"""Post-program instructor rating routes (2026-09) —
`/instructor-assessment/ratings/*`. Gated to `require_operations` for now
(the "Project Lead" role question is explicitly parked pending the
product owner — see the design conversation; swapping in a dedicated role
later is a one-line change here, not a schema change).
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.instructor_assessment.rating import InstructorProgramRating
from app.models.sessions.cohort import Cohort
from app.models.user import User
from app.schemas.instructor_assessment import InstructorProgramRatingIn, InstructorProgramRatingOut
from app.services.instructor_assessment.performance import overall_rating

router = APIRouter(
    prefix="/instructor-assessment/ratings", tags=["instructor-assessment-ratings"],
    dependencies=[Depends(require_operations)],
)


def _rating_out(rating: InstructorProgramRating) -> InstructorProgramRatingOut:
    return InstructorProgramRatingOut(
        id=rating.id, cohort_id=rating.cohort_id, instructor_user_id=rating.instructor_user_id,
        rater_user_id=rating.rater_user_id, dimension_scores=rating.dimension_scores,
        overall_rating=overall_rating(rating.dimension_scores),
        strengths=rating.strengths, areas_for_improvement=rating.areas_for_improvement,
        recommended=rating.recommended, flag=rating.flag, submitted=rating.submitted,
        created_at=rating.created_at, submitted_at=rating.submitted_at,
    )


@router.get("/{cohort_id}/{instructor_user_id}", response_model=InstructorProgramRatingOut | None)
async def get_rating(
    cohort_id: uuid.UUID, instructor_user_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    current: User = Depends(require_operations),
):
    """This rater's own row for this (cohort, instructor) — a draft if not
    yet submitted, so the form can resume where they left off."""
    rating = (await db.execute(
        select(InstructorProgramRating).where(
            InstructorProgramRating.cohort_id == cohort_id,
            InstructorProgramRating.instructor_user_id == instructor_user_id,
            InstructorProgramRating.rater_user_id == current.id,
        )
    )).scalars().first()
    return _rating_out(rating) if rating else None


@router.put("/{cohort_id}/{instructor_user_id}", response_model=InstructorProgramRatingOut)
async def upsert_rating(
    cohort_id: uuid.UUID, instructor_user_id: uuid.UUID, body: InstructorProgramRatingIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_operations),
):
    """Autosave keeps calling this with `submit=False`; a deliberate submit
    sets `submit=True`. `submitted` only ever ratchets forward — once
    submitted, later autosave-shaped calls are refused rather than silently
    reopening a finished rating (same contract as `CompetitionScore`)."""
    if await db.get(Cohort, cohort_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    rating = (await db.execute(
        select(InstructorProgramRating).where(
            InstructorProgramRating.cohort_id == cohort_id,
            InstructorProgramRating.instructor_user_id == instructor_user_id,
            InstructorProgramRating.rater_user_id == current.id,
        )
    )).scalars().first()
    if rating is not None and rating.submitted:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This rating is already submitted")

    if rating is None:
        rating = InstructorProgramRating(
            id=uuid.uuid4(), cohort_id=cohort_id, instructor_user_id=instructor_user_id,
            rater_user_id=current.id, dimension_scores={},
        )
        db.add(rating)

    rating.dimension_scores = body.dimension_scores
    rating.strengths = body.strengths
    rating.areas_for_improvement = body.areas_for_improvement
    rating.recommended = body.recommended
    rating.flag = body.flag
    if body.submit:
        rating.submitted = True
        rating.submitted_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(rating)
    return _rating_out(rating)
