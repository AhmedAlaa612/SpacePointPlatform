"""Instructor Performance Profile — every number here is computed live from
source tables, never stored as a running total (the "derive, never cache"
convention every other leaderboard/aggregate in this codebase follows —
`services/sessions/openings.py::openings_for_session`, the games/competition
leaderboards, etc.).

"Delivered" means present + approved (`InstructorSessionDay.att_status ==
'present' and status == 'approved'`) — the platform's own existing
definition of "a paid day" (see that model's docstring) — not merely
assigned. One decision answers sessions/hours delivered and the reliability
ratio consistently.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructor_assessment.attempt import AssessmentAttempt
from app.models.instructor_assessment.rating import RATING_DIMENSIONS, InstructorCertificationTag, InstructorProgramRating
from app.models.sessions.checklist import InstructorSessionDay
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_call import CohortCall
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.sessions.openings import resolve_duration


def overall_rating(dimension_scores: dict[str, int]) -> float:
    values = [dimension_scores.get(k) for k in RATING_DIMENSIONS if dimension_scores.get(k) is not None]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


async def _delivered_session_ids(db: AsyncSession, user_id: UUID) -> list[UUID]:
    """Sessions this instructor actually delivered — present, and the day
    approved by ops. Assigned-but-never-checked-in or sent-back days don't
    count."""
    return list((await db.execute(
        select(InstructorSessionDay.session_id).where(
            InstructorSessionDay.user_id == user_id,
            InstructorSessionDay.att_status == "present",
            InstructorSessionDay.status == "approved",
        )
    )).scalars().all())


async def get_performance(db: AsyncSession, user_id: UUID) -> dict:
    delivered_session_ids = await _delivered_session_ids(db, user_id)

    total_assigned_ids = (await db.execute(
        select(SessionInstructor.session_id).where(SessionInstructor.user_id == user_id)
    )).scalars().all()

    total_hours = 0.0
    program_ids: set[UUID] = set()
    if delivered_session_ids:
        rows = (await db.execute(
            select(Session, Cohort.program_id)
            .join(Cohort, Cohort.id == Session.cohort_id)
            .where(Session.id.in_(delivered_session_ids))
        )).all()
        for session, program_id in rows:
            hours = await resolve_duration(db, session)
            if hours is not None:
                total_hours += float(hours)
            if program_id is not None:
                program_ids.add(program_id)

    reliability_ratio: Optional[float] = None
    if total_assigned_ids:
        reliability_ratio = round(len(delivered_session_ids) / len(total_assigned_ids), 3)

    rating_rows = (await db.execute(
        select(InstructorProgramRating, Cohort.name, Program.name, User.full_name)
        .join(Cohort, Cohort.id == InstructorProgramRating.cohort_id)
        .outerjoin(Program, Program.id == Cohort.program_id)
        .outerjoin(User, User.id == InstructorProgramRating.rater_user_id)
        .where(InstructorProgramRating.instructor_user_id == user_id, InstructorProgramRating.submitted.is_(True))
        .order_by(InstructorProgramRating.submitted_at.asc())
    )).all()

    rating_history = [
        {
            "rating_id": rating.id, "cohort_id": rating.cohort_id,
            "program_name": program_name or cohort_name,
            "rater_name": rater_name,
            "overall_rating": overall_rating(rating.dimension_scores),
            "recommended": rating.recommended, "flag": rating.flag,
            "strengths": rating.strengths, "areas_for_improvement": rating.areas_for_improvement,
            "submitted_at": rating.submitted_at,
        }
        for rating, cohort_name, program_name, rater_name in rating_rows
    ]
    recent_trend = [r["overall_rating"] for r in rating_history[-6:]]
    average_rating = (
        round(sum(r["overall_rating"] for r in rating_history) / len(rating_history), 2)
        if rating_history else None
    )

    attempts = (await db.execute(
        select(AssessmentAttempt)
        .where(AssessmentAttempt.user_id == user_id, AssessmentAttempt.status == "submitted")
        .order_by(AssessmentAttempt.submitted_at.desc())
    )).scalars().all()

    quiz_history = []
    for attempt in attempts:
        call = await db.get(CohortCall, attempt.cohort_call_id)
        cohort = await db.get(Cohort, call.cohort_id) if call else None
        program = await db.get(Program, cohort.program_id) if cohort and cohort.program_id else None
        quiz_history.append({
            "attempt_id": attempt.id, "cohort_id": cohort.id if cohort else None,
            "program_name": (program.name if program else None) or (cohort.name if cohort else ""),
            "score": attempt.score, "total": attempt.total,
            "critical_correct": attempt.critical_correct, "critical_total": attempt.critical_total,
            "submitted_at": attempt.submitted_at,
        })

    certifications = (await db.execute(
        select(InstructorCertificationTag).where(InstructorCertificationTag.user_id == user_id)
        .order_by(InstructorCertificationTag.created_at.desc())
    )).scalars().all()

    return {
        "user_id": user_id,
        "total_sessions_delivered": len(delivered_session_ids),
        "total_hours_delivered": round(total_hours, 1),
        "programs_participated_in": len(program_ids),
        "average_rating": average_rating,
        "recent_rating_trend": recent_trend,
        "reliability_ratio": reliability_ratio,
        "certifications": certifications,
        "quiz_history": quiz_history,
        "rating_history": rating_history,
    }
