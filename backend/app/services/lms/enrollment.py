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

from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.course import Course
from app.models.lms.enrollment import Enrollment

EnrollmentSource = Literal["self", "ops", "registration"]


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


async def enroll(
    db: AsyncSession,
    *,
    user_id: UUID,
    course_id: UUID,
    source: EnrollmentSource = "self",
    program_id: UUID | None = None,
    registration_id: UUID | None = None,
) -> Enrollment:
    """Grant (or re-grant) a student access to a course.

    Idempotent: an existing active enrollment is returned unchanged — its
    provenance is never rewritten, because only the first path in is recorded
    (§2). An inactive one is reactivated in place (a reinstated registration
    keeps the same row and the same origin). Returns the enrollment; the
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
        if existing.status == "inactive":
            existing.status = "active"
            await db.flush()
        return existing

    enrollment = Enrollment(
        id=uuid4(),
        user_id=user_id,
        course_id=course_id,
        source=source,
        program_id=program_id,
        registration_id=registration_id,
        status="active",
    )
    db.add(enrollment)
    await db.flush()
    return enrollment