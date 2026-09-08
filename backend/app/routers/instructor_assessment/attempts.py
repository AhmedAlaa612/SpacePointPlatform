"""Instructor-facing assessment attempt routes (2026-09) —
`/instructor-assessment/attempts/*`. Same auth population as registering
interest itself (`require_instructor_or_facilitator`).
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_instructor_or_facilitator
from app.db.session import get_db
from app.models.instructor_assessment.attempt import AssessmentAttempt
from app.models.user import User
from app.schemas.instructor_assessment import (
    AttemptAnswerIn,
    AttemptOut,
    AttemptQuestionOut,
    AttemptQuestionReviewOut,
    AttemptResultOut,
)
from app.services.instructor_assessment.attempts import (
    get_attempt_questions,
    get_attempt_review,
    get_own_attempt,
    start_attempt,
    submit_attempt,
)

router = APIRouter(
    prefix="/instructor-assessment/attempts", tags=["instructor-assessment-attempts"],
    dependencies=[Depends(require_instructor_or_facilitator)],
)


async def _attempt_out(db: AsyncSession, attempt: AssessmentAttempt) -> AttemptOut:
    questions = await get_attempt_questions(db, attempt)
    return AttemptOut(
        id=attempt.id, cohort_call_id=attempt.cohort_call_id, status=attempt.status, total=attempt.total,
        questions=[AttemptQuestionOut(**q) for q in questions],
    )


async def _attempt_or_404(db: AsyncSession, attempt_id: uuid.UUID, user: User) -> AssessmentAttempt:
    attempt = await db.get(AssessmentAttempt, attempt_id)
    if attempt is None or attempt.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    return attempt


@router.post("/{cohort_call_id}/start", response_model=AttemptOut)
async def start(
    cohort_call_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    current: User = Depends(require_instructor_or_facilitator),
):
    """Get-or-create — safe to call again on a page refresh mid-attempt;
    the same drawn questions and option order come back every time."""
    attempt = await start_attempt(db, cohort_call_id=cohort_call_id, user=current)
    await db.commit()
    return await _attempt_out(db, attempt)


@router.get("/{cohort_call_id}", response_model=Optional[AttemptOut])
async def get_mine(
    cohort_call_id: uuid.UUID, db: AsyncSession = Depends(get_db),
    current: User = Depends(require_instructor_or_facilitator),
):
    attempt = await get_own_attempt(db, cohort_call_id, current.id)
    if attempt is None:
        return None
    return await _attempt_out(db, attempt)


@router.post("/{attempt_id}/submit", response_model=AttemptResultOut)
async def submit(
    attempt_id: uuid.UUID, body: AttemptAnswerIn, db: AsyncSession = Depends(get_db),
    current: User = Depends(require_instructor_or_facilitator),
):
    attempt = await _attempt_or_404(db, attempt_id, current)
    attempt = await submit_attempt(db, attempt, body.answers)
    try:
        await db.commit()
    except IntegrityError:
        # Two concurrent submits (a double-click) can both pass the
        # not-yet-submitted check before either commits — the loser's
        # AssessmentAnswer inserts collide with the winner's. Rolling back
        # expires our in-memory attempt, so re-fetching gives the winner's
        # committed, already-graded result rather than a 500.
        await db.rollback()
        attempt = await _attempt_or_404(db, attempt_id, current)
        if attempt.status != "submitted":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This attempt is already submitted") from None
    review = await get_attempt_review(db, attempt)
    return AttemptResultOut(
        id=attempt.id, status=attempt.status, score=attempt.score, total=attempt.total,
        critical_correct=attempt.critical_correct, critical_total=attempt.critical_total,
        category_breakdown=attempt.category_breakdown, submitted_at=attempt.submitted_at,
        questions=[AttemptQuestionReviewOut(**q) for q in review],
    )
