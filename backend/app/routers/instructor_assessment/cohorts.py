"""Assign/clear which assessment config gates a cohort's open calls
(2026-09) — the on/off switch described in `AssessmentCohortAssignment`'s
docstring. `/instructor-assessment/cohorts/{cohort_id}/config`. Gated to
`require_operations`, matching `STAFFING_SELECTOR_ROLES`
(`services/sessions/staffing.py`) — who can open a call / select
instructors is who decides whether one needs an assessment first.
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.instructor_assessment.config import AssessmentConfig
from app.models.sessions.cohort import Cohort
from app.models.user import User
from app.schemas.instructor_assessment import AssessmentCohortAssignmentIn, AssessmentCohortAssignmentOut

router = APIRouter(
    prefix="/instructor-assessment/cohorts", tags=["instructor-assessment-cohorts"],
    dependencies=[Depends(require_operations)],
)


async def _assignment_out(db: AsyncSession, assignment: AssessmentCohortAssignment) -> AssessmentCohortAssignmentOut:
    config = await db.get(AssessmentConfig, assignment.config_id)
    return AssessmentCohortAssignmentOut(
        cohort_id=assignment.cohort_id, config_id=assignment.config_id,
        config_name=config.name if config else "", assigned_by=assignment.assigned_by,
        created_at=assignment.created_at,
    )


@router.get("/{cohort_id}/config", response_model=Optional[AssessmentCohortAssignmentOut])
async def get_cohort_assignment(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    assignment = (await db.execute(
        select(AssessmentCohortAssignment).where(AssessmentCohortAssignment.cohort_id == cohort_id)
    )).scalars().first()
    if assignment is None:
        return None
    return await _assignment_out(db, assignment)


@router.put("/{cohort_id}/config", response_model=AssessmentCohortAssignmentOut)
async def set_cohort_assignment(
    cohort_id: uuid.UUID, body: AssessmentCohortAssignmentIn, db: AsyncSession = Depends(get_db),
    current: User = Depends(require_operations),
):
    if await db.get(Cohort, cohort_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    if await db.get(AssessmentConfig, body.config_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assessment config not found")

    assignment = (await db.execute(
        select(AssessmentCohortAssignment).where(AssessmentCohortAssignment.cohort_id == cohort_id)
    )).scalars().first()
    if assignment is None:
        assignment = AssessmentCohortAssignment(
            id=uuid.uuid4(), cohort_id=cohort_id, config_id=body.config_id, assigned_by=current.id,
        )
        db.add(assignment)
    else:
        assignment.config_id = body.config_id
        assignment.assigned_by = current.id
    await db.commit()
    await db.refresh(assignment)
    return await _assignment_out(db, assignment)


@router.delete("/{cohort_id}/config", status_code=status.HTTP_204_NO_CONTENT)
async def clear_cohort_assignment(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Turns the gate back off. Instructors who already registered interest
    while it was on keep whatever attempt they made — this only stops the
    requirement from applying to *new* registrations."""
    assignment = (await db.execute(
        select(AssessmentCohortAssignment).where(AssessmentCohortAssignment.cohort_id == cohort_id)
    )).scalars().first()
    if assignment is not None:
        await db.delete(assignment)
        await db.commit()
