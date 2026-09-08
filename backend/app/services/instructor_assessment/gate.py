"""The assessment gate: whether registering interest on a given opportunity
requires a submitted `AssessmentAttempt` first. Kept separate from
`attempts.py` so `services/sessions/staffing.py` and `cohort_staffing.py`
only need one small, focused import each.

Anchored on `cohort_call_id`, not `InstructorInterest`/`CohortCallInterest`
directly — every open call (even a lone single-session one) already belongs
to a `CohortCall` (`services/sessions/staffing.py::_find_or_create_open_cohort_call`,
2026-08-30), so this one check covers both the direct-session-interest path
and the cohort-wide path.
"""

from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.instructor_assessment.attempt import AssessmentAttempt
from app.models.sessions.cohort_call import CohortCall
from app.models.sessions.session_call import SessionCall


async def resolve_cohort_call_id_for_session(db: AsyncSession, session_id: UUID) -> Optional[UUID]:
    """The cohort_call this session's current open call belongs to, if any.
    Most-recently-opened wins on the rare session that somehow has more than
    one open call grouped under different cohort calls (a mismatched-
    audience edge case — see `_find_or_create_open_cohort_call`'s docstring,
    which normally prevents this by reusing a same-audience call)."""
    return await db.scalar(
        select(SessionCall.cohort_call_id)
        .where(
            SessionCall.session_id == session_id, SessionCall.status == "open",
            SessionCall.cohort_call_id.isnot(None),
        )
        .order_by(SessionCall.created_at.desc())
        .limit(1)
    )


async def assert_assessment_passed(db: AsyncSession, cohort_call_id: Optional[UUID], user_id: UUID) -> None:
    """Refuses interest registration if this opportunity has an assessment
    assigned and this instructor hasn't submitted it yet. A cohort with no
    `AssessmentCohortAssignment` (the default, and every cohort that never
    opts in) is a no-op — nothing about the existing staffing marketplace
    changes for it."""
    if cohort_call_id is None:
        return
    call = await db.get(CohortCall, cohort_call_id)
    if call is None:
        return

    assignment = (await db.execute(
        select(AssessmentCohortAssignment).where(AssessmentCohortAssignment.cohort_id == call.cohort_id)
    )).scalars().first()
    if assignment is None:
        return

    attempt = (await db.execute(
        select(AssessmentAttempt).where(
            AssessmentAttempt.cohort_call_id == cohort_call_id, AssessmentAttempt.user_id == user_id,
        )
    )).scalars().first()
    if attempt is None or attempt.status != "submitted":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Complete the instructor assessment for this opportunity before registering interest",
        )


async def is_assessment_required(db: AsyncSession, cohort_call_id: Optional[UUID], user_id: UUID) -> bool:
    """Non-raising twin of `assert_assessment_passed`, for display — "does
    this instructor still need to take an assessment before they can apply
    here?" so the apply screen can offer the right button up front instead
    of failing on submit."""
    if cohort_call_id is None:
        return False
    call = await db.get(CohortCall, cohort_call_id)
    if call is None:
        return False
    assignment = (await db.execute(
        select(AssessmentCohortAssignment).where(AssessmentCohortAssignment.cohort_id == call.cohort_id)
    )).scalars().first()
    if assignment is None:
        return False
    attempt = (await db.execute(
        select(AssessmentAttempt).where(
            AssessmentAttempt.cohort_call_id == cohort_call_id, AssessmentAttempt.user_id == user_id,
        )
    )).scalars().first()
    return attempt is None or attempt.status != "submitted"
