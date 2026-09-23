"""Student-facing competition surface — `/competitions/student/*`.
Allows authenticated learners to see their own team's competition results
and qualification status once results are published. Strictly preserves
judge blindness and peer anonymity.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.competitions import CompetitionStudentResultOut
from app.services.competitions.judging import get_student_team_result

router = APIRouter(
    prefix="/competitions/student",
    tags=["competitions-student"],
    dependencies=[Depends(get_current_active_user)],
)


@router.get("/cohorts/{cohort_id}/my-result", response_model=CompetitionStudentResultOut)
async def get_my_cohort_competition_result(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    result = await get_student_team_result(db, cohort_id=cohort_id, user_id=current.id)
    return CompetitionStudentResultOut(**result)


@router.get("/cohorts/{cohort_id}/timing-window")
async def get_cohort_timing_window(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    from app.models.sessions.cohort import Cohort
    from app.services.competitions.timing_windows import get_current_active_window
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    windows = cohort.submission_windows or []
    active = get_current_active_window(windows)
    return {
        "windows": windows,
        "active_window": active,
    }

