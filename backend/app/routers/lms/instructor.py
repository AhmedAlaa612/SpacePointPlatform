"""Cohort-scoped instructor LMS Program checklist view (2026-08-21) —
`/lms/instructor/*`. Mirrors `routers/missions/instructor.py`'s cohort_access
pattern for the new checklist entity: instructors track their own cohort's
students without becoming ops/facilitator generally. `require_instructor_missions`
is reused as-is — same role population (instructor/facilitator/operations,
admin bypasses) an LMS-side instructor view needs, no reason to duplicate it.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_instructor_missions
from app.db.session import get_db
from app.models.user import User
from app.schemas.lms_instructor import LmsProgramRosterRowOut
from app.services.lms.program import cohort_program_roster, confirm_program_item
from app.services.missions.cohort_access import require_cohort_access

router = APIRouter(prefix="/lms/instructor", tags=["lms-instructor"], dependencies=[Depends(require_instructor_missions)])


@router.get("/cohorts/{cohort_id}/program-progress", response_model=list[LmsProgramRosterRowOut])
async def cohort_program_progress(
    cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    return await cohort_program_roster(db, cohort_id=cohort_id)


@router.post(
    "/cohorts/{cohort_id}/program-progress/{assignment_id}/items/{item_id}/confirm",
    response_model=LmsProgramRosterRowOut,
)
async def confirm_checklist_item(
    cohort_id: uuid.UUID, assignment_id: uuid.UUID, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Ops/instructor sign-off for a `requires_confirmation` item — the
    review-queue-shaped action for whatever the system can't auto-track
    (a meeting attendance, a manual check-off)."""
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    progress = await confirm_program_item(
        db, assignment_id=assignment_id, item_id=item_id, confirmed_by_user_id=current.id,
    )
    if progress is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Checklist item not found")
    await db.commit()
    roster = await cohort_program_roster(db, cohort_id=cohort_id)
    row = next((r for r in roster if r["assignment_id"] == assignment_id), None)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return row
