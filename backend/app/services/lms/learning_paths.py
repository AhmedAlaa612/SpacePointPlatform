"""LMS learning-path progress (LMS redesign, 2026-08-08) — the rollup layer
on top of `learning_path_steps` + LM1-2's `course_completion`.

No new completion logic lives here: a step's course is "done" exactly when
`course_completion` already says so. This module only derives per-step
*display state* and the path-level rollup, following the same "derive, never
cache" discipline as the rest of `services/lms/`.

State precedence per step (matches design 4a "The ledger"):
  1. `course.kind == "mission"` -> always "mission" (Phase 2 content; not
     playable yet, so it never becomes "done" or blocks "current" from
     landing on the next course-kind step).
  2. course-completed -> "done".
  3. the first not-done, non-mission step in position order -> "current".
  4. everything else -> "locked" (display-only — see model docstring; a
     locked step's course is not access-gated any differently than usual).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.course import Course, CourseModule, ModuleItem, ModuleVideo
from app.models.lms.learning_path import LearningPathStep
from app.services.lms.progress import course_completion


async def path_step_courses(db: AsyncSession, steps: list[LearningPathStep]) -> dict[uuid.UUID, Course]:
    if not steps:
        return {}
    rows = (await db.execute(
        select(Course).where(Course.id.in_([s.course_id for s in steps]))
    )).scalars().all()
    return {c.id: c for c in rows}


async def path_total_duration_seconds(db: AsyncSession, course_ids: list[uuid.UUID]) -> int:
    """Sum of every video item's duration across a set of courses — same
    aggregation LMS_REDESIGN_FOLLOWUPS.md #2 already scoped as "derivable,
    no schema change" for the course landing page, reused here at path
    level."""
    if not course_ids:
        return 0
    total = await db.scalar(
        select(func.coalesce(func.sum(ModuleVideo.duration_seconds), 0))
        .join(ModuleItem, ModuleItem.id == ModuleVideo.item_id)
        .join(CourseModule, CourseModule.id == ModuleItem.module_id)
        .where(CourseModule.course_id.in_(course_ids))
    )
    return int(total or 0)


async def path_progress(
    db: AsyncSession, *, user_id: uuid.UUID, steps: list[LearningPathStep]
) -> dict:
    """Per-step state + overall pct for one student against one path's
    ordered steps. `steps` must already be ordered by position."""
    courses_by_id = await path_step_courses(db, steps)

    step_rows: list[dict] = []
    current_assigned = False
    modules_done_total = 0
    modules_total_total = 0

    for step in steps:
        course = courses_by_id.get(step.course_id)
        if course is None:
            continue
        is_mission = course.kind == "mission"

        if is_mission:
            state = "mission"
            pct = 0
            modules_done, modules_total = 0, 0
        else:
            completion = await course_completion(db, user_id=user_id, course_id=course.id)
            modules_total = len(completion["modules"])
            modules_done = sum(1 for m in completion["modules"] if m["completed"])
            modules_done_total += modules_done
            modules_total_total += modules_total
            done = completion["completed"] and modules_total > 0
            pct = round(100 * modules_done / modules_total) if modules_total else 0

            if done:
                state = "done"
            elif not current_assigned:
                state = "current"
                current_assigned = True
            else:
                state = "locked"

        step_rows.append({
            "position": step.position,
            "course_id": course.id,
            "title": course.title,
            "kind": course.kind,
            "state": state,
            "pct": pct,
            "modules_done": modules_done,
            "modules_total": modules_total,
        })

    overall_pct = round(100 * modules_done_total / modules_total_total) if modules_total_total else 0
    course_count = sum(1 for r in step_rows if r["kind"] != "mission")
    mission_count = sum(1 for r in step_rows if r["kind"] == "mission")

    return {
        "steps": step_rows,
        "pct": overall_pct,
        "course_count": course_count,
        "mission_count": mission_count,
    }
