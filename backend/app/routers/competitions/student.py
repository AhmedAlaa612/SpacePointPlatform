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
    checkpoint_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    from app.models.sessions.cohort import Cohort
    from app.services.competitions.timing_windows import (
        filter_windows_for_gate,
        get_current_active_window,
        is_cohort_deadline_passed,
    )
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    all_windows = cohort.submission_windows or []

    if checkpoint_id is not None:
        target_cid = None if checkpoint_id == "final" else checkpoint_id
        gate_windows = filter_windows_for_gate(all_windows, target_cid)
        active = get_current_active_window(all_windows, checkpoint_id=target_cid)
        deadline_passed = is_cohort_deadline_passed(all_windows, checkpoint_id=target_cid)
        deadline_window = next((w for w in gate_windows if isinstance(w, dict) and w.get("is_deadline")), None)
        return {
            "windows": gate_windows,
            "active_window": active,
            "is_deadline_passed": deadline_passed,
            "deadline_cutoff_at": deadline_window.get("cutoff_at") if deadline_window else None,
        }

    # Default: Final Gate windows at top level + checkpoints map
    final_windows = filter_windows_for_gate(all_windows, None)
    active = get_current_active_window(all_windows, checkpoint_id=None)
    deadline_passed = is_cohort_deadline_passed(all_windows, checkpoint_id=None)
    deadline_window = next((w for w in final_windows if isinstance(w, dict) and w.get("is_deadline")), None)

    # Group checkpoints
    checkpoints_map = {}
    for w in all_windows:
        if isinstance(w, dict) and w.get("checkpoint_id") and w.get("checkpoint_id") != "final":
            cid = str(w["checkpoint_id"])
            if cid not in checkpoints_map:
                cp_windows = filter_windows_for_gate(all_windows, cid)
                cp_active = get_current_active_window(all_windows, checkpoint_id=cid)
                cp_dead_passed = is_cohort_deadline_passed(all_windows, checkpoint_id=cid)
                cp_dead_win = next((cw for cw in cp_windows if isinstance(cw, dict) and cw.get("is_deadline")), None)
                checkpoints_map[cid] = {
                    "windows": cp_windows,
                    "active_window": cp_active,
                    "is_deadline_passed": cp_dead_passed,
                    "deadline_cutoff_at": cp_dead_win.get("cutoff_at") if cp_dead_win else None,
                }

    return {
        "windows": final_windows,
        "all_windows": all_windows,
        "active_window": active,
        "is_deadline_passed": deadline_passed,
        "deadline_cutoff_at": deadline_window.get("cutoff_at") if deadline_window else None,
        "checkpoints": checkpoints_map,
    }

