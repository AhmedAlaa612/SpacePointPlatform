"""Student & Team endpoints for the Interactive Card Hint Station."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.lms.program import LmsProgram, LmsProgramAssignment
from app.models.sessions.cohort import Cohort
from app.models.team import Team, TeamMember
from app.models.user import User
from app.schemas.hint_station import (
    CohortHintCardOut,
    StudentHintStationOut,
)
from app.services.competitions.hint_station import (
    get_effective_cohort_challenges,
    reveal_hint_card,
)

router = APIRouter(prefix="/lms", tags=["lms-hints"])


@router.get("/programs/{assignment_id}/hints", response_model=StudentHintStationOut)
async def get_program_hints(
    assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Loads Hint Station for the student's assignment, scoped to their team."""
    assignment = await db.get(LmsProgramAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program assignment not found")

    # Verify student owns this assignment or is staff
    # User is multi-role — check role_values, not a nonexistent .role.
    is_staff = any(r in current.role_values for r in ("admin", "instructor", "judge", "operations"))
    if assignment.user_id != current.id and not is_staff:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

    cohort_id = assignment.cohort_id
    if not cohort_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Assignment is not attached to a cohort")

    cohort = await db.get(Cohort, cohort_id)
    cohort_name = cohort.name if cohort else None

    # Resolve program info
    lms_program = await db.get(LmsProgram, assignment.lms_program_id)
    program_name = lms_program.name if lms_program else None
    program_id = lms_program.program_id if lms_program else None

    # Resolve team in this cohort
    team = await db.scalar(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == current.id, Team.cohort_id == cohort_id)
    )

    team_id = team.id if team else None
    team_name = team.name if team else None

    # Load challenges with lock and reveal status computed for this team
    challenges = await get_effective_cohort_challenges(
        db,
        cohort_id=cohort_id,
        user=current,
        team_id=team_id,
        is_authoring=False,
    )

    total_hints_revealed = 0
    total_deducted = 0
    for ch in challenges:
        for c in ch.cards:
            if c.is_revealed:
                total_hints_revealed += 1
                total_deducted += c.point_deduction

    can_switch_to_judge = is_staff or assignment.mode == "observer"

    return StudentHintStationOut(
        cohort_id=cohort_id,
        cohort_name=cohort_name,
        program_id=program_id,
        program_name=program_name,
        team_id=team_id,
        team_name=team_name,
        is_active=True,
        challenges=challenges,
        total_hints_revealed=total_hints_revealed,
        total_points_deducted=total_deducted,
        can_switch_to_judge_view=can_switch_to_judge,
    )


@router.post("/programs/{assignment_id}/hints/{card_id}/reveal", response_model=CohortHintCardOut)
async def unlock_hint(
    assignment_id: uuid.UUID,
    card_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Unlocks a hint card for the team and records point deduction."""
    assignment = await db.get(LmsProgramAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program assignment not found")

    is_staff = any(r in current.role_values for r in ("admin", "instructor", "judge", "operations"))
    if assignment.user_id != current.id and not is_staff:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Access denied")

    cohort_id = assignment.cohort_id
    if not cohort_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Assignment is not attached to a cohort")

    team = await db.scalar(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == current.id, Team.cohort_id == cohort_id)
    )

    team_id = team.id if team else None

    return await reveal_hint_card(
        db,
        cohort_id=cohort_id,
        card_id=card_id,
        user=current,
        team_id=team_id,
    )
