"""Student & instructor routes for SpacePoint Mission Arcade (`/lms/arcade/*`)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.lms.program import LmsProgramAssignment, LmsProgramItem
from app.models.user import User
from app.schemas.lms_arcade import ArcadeAttemptOut, ArcadeAttemptSubmitIn, ArcadeGameCatalogOut
from app.services.lms import arcade as arcade_service
from app.services.missions.cohort_access import require_cohort_access

router = APIRouter(prefix="/lms/arcade", tags=["lms-arcade"])


@router.get("/games", response_model=list[ArcadeGameCatalogOut])
async def get_arcade_catalog(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    return await arcade_service.list_games_for_user(db, user_id=current.id)


@router.post("/games/{game_key}/attempts", response_model=ArcadeAttemptOut, status_code=status.HTTP_201_CREATED)
async def submit_arcade_attempt(
    game_key: str,
    body: ArcadeAttemptSubmitIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    return await arcade_service.record_arcade_attempt(db, user_id=current.id, game_key=game_key, body=body)


@router.get(
    "/cohorts/{cohort_id}/assignments/{assignment_id}/items/{item_id}/best-attempt",
    response_model=ArcadeAttemptOut,
)
async def get_student_arcade_item_attempt(
    cohort_id: uuid.UUID,
    assignment_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Instructor/ops drill-in on the Progress tab to inspect a student's best
    run (score, accuracy, elapsed time, and debrief notes) for an arcade_game
    checklist item."""
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    assignment = await db.get(LmsProgramAssignment, assignment_id)
    item = await db.get(LmsProgramItem, item_id)
    if assignment is None or item is None or item.arcade_game_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item or assignment not found")
    best = await arcade_service.get_best_attempt_for_user(
        db, user_id=assignment.user_id, game_id=item.arcade_game_id, mode=item.arcade_game_mode,
    )
    if best is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No attempt recorded yet")
    return best
