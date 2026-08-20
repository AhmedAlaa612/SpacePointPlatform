"""LMS enrollment service (LM1-2) — the access gate (D8).

`UNIQUE(user_id, course_id)` makes enrollment naturally idempotent at the
schema level; this function is the friendly read of that constraint. A
cancelled registration can flip an enrollment to `inactive` (LM1-7); calling
enroll again is how it comes back. `program_id`/`registration_id` record only
how the row STARTED — as the model docstring says, read them as provenance,
never live membership, so a reactivated enrollment never overwrites the path
it began on.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.course import Course
from app.models.lms.enrollment import Enrollment

EnrollmentSource = Literal["self", "ops", "registration", "purchase"]


def enrollment_is_active() -> tuple:
    """`Enrollment.status == 'active'` AND not expired — the one predicate
    every enrollment gate or listing should use (P1-3, audit §9.3(c)).
    `expires_at IS NULL` is perpetual, never a `9999` sentinel. Splice into a
    `.where(Enrollment.user_id == ..., *enrollment_is_active())`; kept as a
    tuple of clauses rather than a single boolean so callers can still add
    their own `.join`/other predicates around it.

    Five call sites read enrollment status/expiry today: `_assert_enrolled`
    (the actual gate), `course_detail`'s own `enrolled` flag, and
    `my_courses_dashboard`'s listing all use this. `_video_from_token`
    delegates to `_assert_enrolled`. `instructor_progress` deliberately does
    not — it's a staff-facing history report, and an expired student's past
    progress is still real progress an instructor should be able to see."""
    return (
        Enrollment.status == "active",
        or_(Enrollment.expires_at.is_(None), Enrollment.expires_at > func.now()),
    )


def _resolve_expires_at(course: Course) -> datetime | None:
    """course.access_days -> a concrete expires_at, computed once at grant
    time and never recomputed (P1-3) — NULL access_days means perpetual,
    never a 9999 sentinel."""
    if course.access_days is None:
        return None
    return datetime.now(timezone.utc) + timedelta(days=course.access_days)


async def enroll(
    db: AsyncSession,
    *,
    user_id: UUID,
    course_id: UUID,
    source: EnrollmentSource = "self",
    program_id: UUID | None = None,
    registration_id: UUID | None = None,
    granted_by: UUID | None = None,
) -> Enrollment:
    """Grant (or re-grant) a student access to a course.

    Idempotent: an existing *active, unexpired* enrollment is returned
    unchanged — its provenance is never rewritten, because only the first
    path in is recorded (§2). An inactive OR expired one is (re)activated in
    place, with expires_at recomputed from the course's current
    access_days — a fresh grant restarts the access window rather than
    inheriting whatever was left of the old one. Returns the enrollment; the
    caller commits.
    """
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, detail="Course not found")

    existing = (await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == user_id,
            Enrollment.course_id == course_id,
        )
    )).scalars().first()

    if existing is not None:
        now_expired = existing.expires_at is not None and existing.expires_at <= datetime.now(timezone.utc)
        if existing.status == "inactive" or now_expired:
            existing.status = "active"
            existing.expires_at = _resolve_expires_at(course)
            if granted_by is not None:
                existing.granted_by = granted_by
            await db.flush()
        return existing

    enrollment = Enrollment(
        id=uuid4(),
        user_id=user_id,
        course_id=course_id,
        source=source,
        program_id=program_id,
        registration_id=registration_id,
        granted_by=granted_by,
        expires_at=_resolve_expires_at(course),
        status="active",
    )
    db.add(enrollment)
    await db.flush()
    return enrollment