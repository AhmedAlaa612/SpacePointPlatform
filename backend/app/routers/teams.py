"""Domain-agnostic team membership routes (2026-08-17) — `/teams/*`.

Not nested under `/missions/teams/*`: the whole point of generalizing
`Team` out of the missions-only `MissionTeam` is that it stops being a
missions concept, and the Competition domain needs to call these same
join/leave endpoints without a `/missions/` prefix. Mission-context team
creation/listing (`POST /missions/teams`, `GET /missions/teams/mine`,
`POST /missions/admin/teams`) stays where it is — those are mission-flow
surfaces, not generic membership mutation, and don't move here.

Explicit status codes, no silent no-ops — same idiom `create_team` already
uses (409 on a name collision): joining an already-joined team is a 409,
not a quiet 200; leaving a team you're not on is a 404, not a quiet 204.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.team import Team
from app.models.user import User
from app.schemas.teams import TeamOut
from app.services.lms.program import sync_team_mission_runs
from app.services.teams import join_team, leave_team, team_member_ids

router = APIRouter(prefix="/teams", tags=["teams"])


async def _team_out(db: AsyncSession, team: Team) -> TeamOut:
    member_ids = await team_member_ids(db, team_id=team.id)
    members = [await db.get(User, uid) for uid in member_ids]
    return TeamOut(
        id=team.id, name=team.name, cohort_id=team.cohort_id, member_ids=member_ids,
        member_names=[m.full_name for m in members if m is not None],
        join_code=getattr(team, "join_code", None),
    )


@router.post("/{team_id}/join", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def join_team_endpoint(
    team_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")
    if current.id in await team_member_ids(db, team_id=team_id):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Already a member of this team")
    if "observer" in current.role_values and not getattr(team, "is_observer", False):
        team.is_observer = True
    await join_team(db, team_id=team_id, user_id=current.id)
    # Picks up any team-scoped LMS checklist item that couldn't be assigned
    # earlier because this team didn't exist/have a member yet — see
    # `sync_team_mission_runs`'s own docstring. A no-op for a cohort-less
    # (self-formed) team or a cohort with no such checklist item.
    await sync_team_mission_runs(db, team=team)
    await db.commit()
    return await _team_out(db, team)


@router.delete("/{team_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_team_endpoint(
    team_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    if current.id not in await team_member_ids(db, team_id=team_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="You are not a member of this team")
    await leave_team(db, team_id=team_id, user_id=current.id)
    await db.commit()
