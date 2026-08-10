"""Mission team primitives (P6-1, Phase 2 Stage 6, 2026-08-11).

Ops-assign (cohort-scoped) and self-form (public catalog, no cohort) both
call `create_team` — "both write the same rows" (MISSIONS_REPORT.md §Q5).
The HTTP surface (who's allowed to call this, and how) is P6-4; this module
only has the data primitives.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.team import MissionTeam, MissionTeamMember


async def create_team(
    db: AsyncSession, *, name: str, created_by: uuid.UUID, cohort_id: uuid.UUID | None = None,
    member_ids: list[uuid.UUID] | None = None,
) -> MissionTeam:
    """Creates a team and adds `member_ids` (deduplicated with `created_by`,
    who is always a member of a team they create). Raises 409 on a name
    collision within the same `cohort_id` — self-formed teams (`cohort_id`
    NULL) never collide by name, there's no scope to dedupe them against.
    """
    team = MissionTeam(id=uuid.uuid4(), name=name, cohort_id=cohort_id, created_by=created_by)
    db.add(team)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise HTTPException(409, detail="A team with this name already exists in this cohort")

    members = {created_by, *(member_ids or [])}
    for user_id in members:
        db.add(MissionTeamMember(mission_team_id=team.id, user_id=user_id))
    await db.flush()
    return team


async def add_member(db: AsyncSession, *, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    existing = await db.get(MissionTeamMember, (team_id, user_id))
    if existing is not None:
        return
    db.add(MissionTeamMember(mission_team_id=team_id, user_id=user_id))
    await db.flush()


async def remove_member(db: AsyncSession, *, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    member = await db.get(MissionTeamMember, (team_id, user_id))
    if member is not None:
        await db.delete(member)
        await db.flush()


async def team_member_ids(db: AsyncSession, *, team_id: uuid.UUID) -> list[uuid.UUID]:
    rows = (await db.execute(
        select(MissionTeamMember.user_id).where(MissionTeamMember.mission_team_id == team_id)
    )).scalars().all()
    return list(rows)


async def teams_for_user(db: AsyncSession, *, user_id: uuid.UUID) -> list[MissionTeam]:
    return list((await db.execute(
        select(MissionTeam)
        .join(MissionTeamMember, MissionTeamMember.mission_team_id == MissionTeam.id)
        .where(MissionTeamMember.user_id == user_id)
        .order_by(MissionTeam.created_at.desc())
    )).scalars().all())
