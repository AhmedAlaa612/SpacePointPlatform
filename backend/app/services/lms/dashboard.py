"""LMS student dashboard (LMS redesign, 2026-08-06) — `/lms/my-courses` and the
landing page's "resume" band. Nothing here stores new state: it's a read-side
aggregation over LM1-2's existing `course_completion`/`unlock_state` plus one
new query (the resume pointer), same "derive, never cache" discipline as the
rest of services/lms/progress.py.

Resume pointer: the item whose `item_progress.updated_at` is most recent,
among the student's active, not-yet-completed enrollments — i.e. "what was I
last touching". No video-position tracking exists (LM1-6 doesn't persist
playback position), so this points at an *item*, not a timestamp within one.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.course import Course, CourseModule, ModuleItem
from app.models.lms.enrollment import Enrollment, ItemProgress
from app.services.lms.enrollment import enrollment_is_active
from app.services.lms.progress import COMPLETED_STATUSES, course_completion


async def _course_summary(db: AsyncSession, *, user_id: uuid.UUID, course: Course) -> dict:
    completion = await course_completion(db, user_id=user_id, course_id=course.id)
    modules_total = len(completion["modules"])
    modules_done = sum(1 for m in completion["modules"] if m["completed"])
    any_progress = any(m["mandatory_completed"] > 0 for m in completion["modules"])

    if completion["completed"] and modules_total > 0:
        status = "completed"
    elif any_progress:
        status = "in_progress"
    else:
        status = "not_started"

    pct = round(100 * modules_done / modules_total) if modules_total else 0
    return {
        "course_id": course.id,
        "title": course.title,
        "kind": course.kind,
        "status": status,
        "modules_done": modules_done,
        "modules_total": modules_total,
        "pct": pct,
    }


async def _resume_pointer(db: AsyncSession, *, user_id: uuid.UUID, course_ids: list[uuid.UUID]) -> dict | None:
    if not course_ids:
        return None

    last = (await db.execute(
        select(ItemProgress, ModuleItem, CourseModule, Course)
        .join(ModuleItem, ModuleItem.id == ItemProgress.item_id)
        .join(CourseModule, CourseModule.id == ModuleItem.module_id)
        .join(Course, Course.id == CourseModule.course_id)
        .where(ItemProgress.user_id == user_id, Course.id.in_(course_ids))
        .order_by(ItemProgress.updated_at.desc())
        .limit(1)
    )).first()

    if last is None:
        # Never touched anything yet — resume at the first module of whichever
        # enrolled course was picked (caller passes courses in enrollment order).
        course = await db.get(Course, course_ids[0])
        module = (await db.execute(
            select(CourseModule).where(CourseModule.course_id == course.id).order_by(CourseModule.position).limit(1)
        )).scalars().first()
        if module is None:
            return None
        item = (await db.execute(
            select(ModuleItem).where(ModuleItem.module_id == module.id).order_by(ModuleItem.position).limit(1)
        )).scalars().first()
        return {
            "course_id": course.id, "course_title": course.title,
            "module_id": module.id, "module_title": module.title,
            "next_item_id": item.id if item else None,
            "mandatory_completed": 0, "mandatory_total": 0,
        }

    _progress, _item, module, course = last

    # The module the student was last in might since be fully done (they
    # finished it right after) — resume at the course's actual open module.
    completion = await course_completion(db, user_id=user_id, course_id=course.id)
    open_row = next((r for r in completion["modules"] if not r["completed"]), None)
    target_module_id = open_row["module_id"] if open_row else module.id

    items = (await db.execute(
        select(ModuleItem).where(ModuleItem.module_id == target_module_id).order_by(ModuleItem.position)
    )).scalars().all()
    progress_rows = (await db.execute(
        select(ItemProgress).where(
            ItemProgress.user_id == user_id, ItemProgress.item_id.in_([i.id for i in items])
        )
    )).scalars().all()
    done_ids = {p.item_id for p in progress_rows if p.status in COMPLETED_STATUSES}
    next_item = next((i for i in items if i.id not in done_ids), items[0] if items else None)
    target_module = await db.get(CourseModule, target_module_id)

    return {
        "course_id": course.id, "course_title": course.title,
        "module_id": target_module.id, "module_title": target_module.title,
        "next_item_id": next_item.id if next_item else None,
        "mandatory_completed": open_row["mandatory_completed"] if open_row else 0,
        "mandatory_total": open_row["mandatory_total"] if open_row else 0,
    }


async def recent_activity(db: AsyncSession, *, user_id: uuid.UUID, limit: int = 10) -> list[dict]:
    """Last N completed items across every course, newest first — the
    profile page's activity feed. Same join shape `_resume_pointer` above
    already uses; read-only, nothing new stored."""
    rows = (await db.execute(
        select(ItemProgress, ModuleItem, CourseModule, Course)
        .join(ModuleItem, ModuleItem.id == ItemProgress.item_id)
        .join(CourseModule, CourseModule.id == ModuleItem.module_id)
        .join(Course, Course.id == CourseModule.course_id)
        .where(ItemProgress.user_id == user_id, ItemProgress.status.in_(COMPLETED_STATUSES))
        .order_by(ItemProgress.completed_at.desc())
        .limit(limit)
    )).all()

    return [
        {
            "item_id": item.id,
            "item_title": item.title,
            "item_kind": item.kind,
            "course_id": course.id,
            "course_title": course.title,
            "completed_at": progress.completed_at,
        }
        for progress, item, _module, course in rows
    ]


async def my_courses_dashboard(db: AsyncSession, *, user_id: uuid.UUID) -> dict:
    rows = (await db.execute(
        select(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(Enrollment.user_id == user_id, *enrollment_is_active())
        .order_by(Enrollment.created_at.desc())
    )).scalars().all()

    summaries = [await _course_summary(db, user_id=user_id, course=c) for c in rows]
    modules_done_total = sum(s["modules_done"] for s in summaries)
    in_progress_count = sum(1 for s in summaries if s["status"] == "in_progress")

    incomplete_course_ids = [s["course_id"] for s in summaries if s["status"] != "completed"]
    resume = await _resume_pointer(db, user_id=user_id, course_ids=incomplete_course_ids)

    return {
        "stats": {
            "in_progress": in_progress_count,
            "total_enrolled": len(summaries),
            "modules_done": modules_done_total,
        },
        "resume": resume,
        "courses": summaries,
    }
