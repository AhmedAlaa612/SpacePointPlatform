"""Instructor LMS progress view (LM1-10) — reuses the exact session-delivery
scoping (`delivery.get_roster` / `_get_deliverable_session`) so "which
students can this instructor see" can never drift from the roster/attendance
view they already have. Ops/facilitators/admin see every session (W5 S5-1's
existing `require_session_delivery` rule); a plain instructor only sees
sessions they're assigned to via `SessionInstructor`.

Progress is read straight off the LM1-2 services (`unlock_state`,
`course_completion`) — nothing here recomputes completion; it only adds the
one query those don't cover, quiz attempts/best-score, and joins it all
against the roster.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms import Course, CourseModule, ItemProgress, ModuleItem
from app.models.sessions.program import Program
from app.models.user import User
from app.services.lms.program import resolve_cohort_program_course_ids
from app.services.lms.progress import course_completion, unlock_state
from app.services.sessions import delivery


async def _quiz_progress(db: AsyncSession, *, user_id: UUID, course_id: UUID) -> list[dict]:
    rows = (await db.execute(
        select(ModuleItem.id, ModuleItem.title, ItemProgress.status, ItemProgress.quiz_attempts, ItemProgress.best_score)
        .select_from(ModuleItem)
        .join(CourseModule, CourseModule.id == ModuleItem.module_id)
        .outerjoin(
            ItemProgress,
            (ItemProgress.item_id == ModuleItem.id) & (ItemProgress.user_id == user_id),
        )
        .where(CourseModule.course_id == course_id, ModuleItem.kind == "quiz")
        .order_by(CourseModule.position, ModuleItem.position)
    )).all()
    return [
        {
            "item_id": item_id, "title": title, "status": status or "not_started",
            "attempts": attempts or 0, "best_score": float(best_score) if best_score is not None else None,
        }
        for item_id, title, status, attempts, best_score in rows
    ]


async def student_course_progress(db: AsyncSession, *, user_id: UUID, course_id: UUID) -> dict:
    modules = await unlock_state(db, user_id=user_id, course_id=course_id)
    completion = await course_completion(db, user_id=user_id, course_id=course_id)
    return {
        "course_id": course_id,
        "completed": completion["completed"],
        "modules": modules,
        "quizzes": await _quiz_progress(db, user_id=user_id, course_id=course_id),
    }


async def session_lms_progress(db: AsyncSession, *, session_id: UUID, user: User) -> dict:
    """The roster for this session (already scoped to the requesting
    instructor by `get_roster`), each row's LMS progress across every
    course item in the cohort's LMS Program checklist (override-aware,
    2026-08-21). A student with no linked LMS account (never enrolled, or
    the registration predates LM1-7) reports `has_lms_account=False` and
    an empty course list — not an error."""
    session, cohort, roster = await delivery.get_roster(db, session_id, user)
    program = await db.get(Program, cohort.program_id)

    course_ids = await resolve_cohort_program_course_ids(db, cohort.id)
    courses = {
        c.id: c for c in (await db.execute(
            select(Course).where(Course.id.in_(course_ids))
        )).scalars().all()
    } if course_ids else {}

    students = []
    for _reg, contact, _att in roster:
        # .order_by: contact_id isn't unique yet (B4/D1, Phase 2 Stage 1
        # fixes it properly) — deterministic ordering means a repeated
        # lookup at least resolves to the same account every time.
        student_user = (await db.execute(
            select(User).where(User.contact_id == contact.id).order_by(User.created_at)
        )).scalars().first()

        course_rows = []
        if student_user is not None:
            for course_id in course_ids:
                row = await student_course_progress(db, user_id=student_user.id, course_id=course_id)
                row["course_title"] = courses[course_id].title if course_id in courses else None
                course_rows.append(row)

        students.append({
            "contact_id": contact.id,
            "student_name": contact.full_name,
            "has_lms_account": student_user is not None,
            "courses": course_rows,
        })

    return {
        "session_id": session.id,
        "cohort_id": cohort.id,
        "program_name": program.name,
        "students": students,
    }
