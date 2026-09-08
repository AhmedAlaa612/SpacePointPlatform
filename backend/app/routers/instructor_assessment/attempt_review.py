"""Ops-facing view of one instructor's assessment answers for one
opportunity (2026-09) — the "view answers" drill-down from both staffing
screens. The single-session eligible-instructors table and the cohort-call
applicant table already show the aggregate quiz score; this reuses the same
per-question review the instructor sees after their own submission
(`services/instructor_assessment/attempts.py::get_attempt_review`), so
there's one review implementation, not two.

Two entry points sharing one lookup: the single-session screen only has
`session_id` on hand, the cohort-call screen already has `cohort_call_id`
directly — same split `gate.py`'s `resolve_cohort_call_id_for_session`
exists for. `/instructor-assessment/attempts/*`, same prefix as the
instructor-facing attempt routes but a separate router instance (its own
`dependencies`), gated to `require_operations` to match the selection
screens themselves rather than `require_instructor_or_facilitator`.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.instructor_assessment.attempt import AssessmentAttempt
from app.schemas.instructor_assessment import AttemptQuestionReviewOut, AttemptResultOut
from app.services.instructor_assessment.attempts import get_attempt_review
from app.services.instructor_assessment.gate import resolve_cohort_call_id_for_session

router = APIRouter(
    prefix="/instructor-assessment/attempts", tags=["instructor-assessment-attempt-review"],
    dependencies=[Depends(require_operations)],
)


async def _review_for(db: AsyncSession, cohort_call_id: uuid.UUID, user_id: uuid.UUID) -> AttemptResultOut:
    attempt = (await db.execute(
        select(AssessmentAttempt).where(
            AssessmentAttempt.cohort_call_id == cohort_call_id, AssessmentAttempt.user_id == user_id,
            AssessmentAttempt.status == "submitted",
        )
    )).scalars().first()
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No submitted assessment attempt found")
    review = await get_attempt_review(db, attempt)
    return AttemptResultOut(
        id=attempt.id, status=attempt.status, score=attempt.score, total=attempt.total,
        critical_correct=attempt.critical_correct, critical_total=attempt.critical_total,
        category_breakdown=attempt.category_breakdown, submitted_at=attempt.submitted_at,
        questions=[AttemptQuestionReviewOut(**q) for q in review],
    )


@router.get("/cohort-calls/{cohort_call_id}/instructors/{user_id}/review", response_model=AttemptResultOut)
async def get_review_for_cohort_call(
    cohort_call_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession = Depends(get_db),
):
    return await _review_for(db, cohort_call_id, user_id)


@router.get("/sessions/{session_id}/instructors/{user_id}/review", response_model=AttemptResultOut)
async def get_review_for_session(session_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    cohort_call_id = await resolve_cohort_call_id_for_session(db, session_id)
    if cohort_call_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No open call on this session")
    return await _review_for(db, cohort_call_id, user_id)
