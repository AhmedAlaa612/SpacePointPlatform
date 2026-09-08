"""The Priority Score blend behind the instructor-selection screen (2026-09).
Computed live, per the active `RankingWeightProfile` — "derive, never
cache", the same convention as every other aggregate in this domain. The
applicant list for one cohort call is always small, so no caching is
needed.

Each factor is normalized to a 0-100 scale before blending, and a factor
with no data for a given instructor (e.g. a first-time applicant with no
rating history yet) is left out of that instructor's blend entirely rather
than counted as zero — the remaining factors' weights are renormalized so a
new instructor isn't punished for lacking history, only scored on what
actually exists for them.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructor_assessment.attempt import AssessmentAttempt
from app.models.instructor_assessment.ranking import RankingWeightProfile
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_call import CohortCall
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.services.instructor_assessment.performance import get_performance


async def get_active_weights(db: AsyncSession) -> dict[str, float]:
    profile = (await db.execute(
        select(RankingWeightProfile).where(RankingWeightProfile.is_active.is_(True))
    )).scalars().first()
    return profile.factor_weights if profile else {}


async def resolve_program_for_cohort_call(db: AsyncSession, cohort_call_id: UUID) -> tuple[Optional[UUID], Optional[str]]:
    call = await db.get(CohortCall, cohort_call_id)
    cohort = await db.get(Cohort, call.cohort_id) if call else None
    if cohort is None or cohort.program_id is None:
        return None, None
    program = await db.get(Program, cohort.program_id)
    return cohort.program_id, (program.program_type if program else None)


async def _count_deliveries(
    db: AsyncSession, user_id: UUID, *, program_id: Optional[UUID] = None, program_type: Optional[str] = None,
) -> int:
    query = (
        select(func.count(func.distinct(Cohort.id)))
        .select_from(SessionInstructor)
        .join(Session, Session.id == SessionInstructor.session_id)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .where(SessionInstructor.user_id == user_id)
    )
    if program_id is not None:
        query = query.where(Cohort.program_id == program_id)
    elif program_type is not None:
        query = query.join(Program, Program.id == Cohort.program_id).where(Program.program_type == program_type)
    return (await db.scalar(query)) or 0


async def compute_relevant_experience_score(
    db: AsyncSession, user_id: UUID, program_id: Optional[UUID], program_type: Optional[str],
) -> Optional[float]:
    """Provisional (explicitly parked pending the product owner's
    confirmation of what "relevant" means): exact-curriculum history counts
    for more than same-type-only history, so a first-timer on this exact
    program isn't scored as zero if they've delivered other programs of the
    same type. Isolated in this one function so the definition can change
    without touching the blend around it."""
    if program_id is None:
        return None
    exact = await _count_deliveries(db, user_id, program_id=program_id)
    same_type = await _count_deliveries(db, user_id, program_type=program_type) if program_type else 0
    return min(exact * 25, 75) + min(same_type * 5, 25)


async def _submitted_attempt(db: AsyncSession, user_id: UUID, cohort_call_id: UUID) -> Optional[AssessmentAttempt]:
    return (await db.execute(
        select(AssessmentAttempt).where(
            AssessmentAttempt.cohort_call_id == cohort_call_id, AssessmentAttempt.user_id == user_id,
            AssessmentAttempt.status == "submitted",
        )
    )).scalars().first()


async def compute_priority_score(
    db: AsyncSession, *, user_id: UUID, cohort_call_id: UUID, weights: dict[str, float],
    perf: Optional[dict] = None, attempt: Optional[AssessmentAttempt] = None,
) -> Optional[float]:
    """`perf` and `attempt` may be passed in pre-fetched (the caller likely
    already needed both for its own display columns) to avoid querying
    either twice per instructor on a roster."""
    if not weights:
        return None

    if attempt is None:
        attempt = await _submitted_attempt(db, user_id, cohort_call_id)
    assessment_score = (attempt.score / attempt.total * 100) if attempt and attempt.total else None

    if perf is None:
        perf = await get_performance(db, user_id)
    previous_rating = (perf["average_rating"] / 5 * 100) if perf["average_rating"] is not None else None
    reliability = (perf["reliability_ratio"] * 100) if perf["reliability_ratio"] is not None else None
    recent_trend = perf["recent_rating_trend"]
    recent_performance = (recent_trend[-1] / 5 * 100) if recent_trend else None
    # Diminishing, capped — 20 delivered sessions already maxes this factor.
    sessions_hours = min(perf["total_sessions_delivered"] * 5, 100)

    program_id, program_type = await resolve_program_for_cohort_call(db, cohort_call_id)
    relevant_experience = await compute_relevant_experience_score(db, user_id, program_id, program_type)

    components = {
        "assessment_score": assessment_score,
        "previous_rating": previous_rating,
        "relevant_experience": relevant_experience,
        "sessions_hours": sessions_hours,
        "reliability": reliability,
        "recent_performance": recent_performance,
    }

    weighted_sum = 0.0
    total_weight = 0.0
    for factor, value in components.items():
        if value is None:
            continue
        w = weights.get(factor, 0)
        weighted_sum += value * w
        total_weight += w
    if total_weight == 0:
        return None
    return round(weighted_sum / total_weight, 1)


async def get_ranking_fields(db: AsyncSession, *, user_id: UUID, cohort_call_id: UUID, weights: dict[str, float]) -> dict:
    """The quiz/performance/priority-score columns shown on both the
    cohort-call applicant table and the single-session eligible-instructor
    table — assembled once so the two screens can't drift out of sync with
    each other, and so `attempt`/`perf` are each fetched only once per row
    rather than once per column that needs them."""
    attempt = await _submitted_attempt(db, user_id, cohort_call_id)
    perf = await get_performance(db, user_id)
    recent_trend = perf["recent_rating_trend"]
    return {
        "quiz_score": round(attempt.score / attempt.total * 100) if attempt and attempt.total else None,
        "quiz_critical_correct": attempt.critical_correct if attempt else None,
        "quiz_critical_total": attempt.critical_total if attempt else None,
        "total_sessions_delivered": perf["total_sessions_delivered"],
        "total_hours_delivered": perf["total_hours_delivered"],
        "average_rating": perf["average_rating"],
        "recent_rating": recent_trend[-1] if recent_trend else None,
        "priority_score": await compute_priority_score(
            db, user_id=user_id, cohort_call_id=cohort_call_id, weights=weights, perf=perf, attempt=attempt,
        ),
    }
