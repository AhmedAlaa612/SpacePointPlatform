"""Team primitives (2026-08-17) — domain-agnostic, generalized out of the
missions-only `app/services/missions/teams.py`. Ops-assign (cohort-scoped)
and self-form (public catalog, no cohort) both call `create_team` — both
write the same rows. Mission-specific attempt/scoring logic (XOR handling,
per-member point awards) stays in `app/services/missions/attempts.py`,
since that's inherently mission-attempt lifecycle, not team identity.

`join_team`/`leave_team` are the first real HTTP-facing membership mutators
— the router (`app/routers/teams.py`) owns the "already a member"/"not a
member" 409/404 checks (via `team_member_ids`) before calling these, so
these two stay simple, idempotent primitives rather than duplicating that
validation here.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team, TeamMember


async def create_team(
    db: AsyncSession, *, name: str, created_by: uuid.UUID, cohort_id: uuid.UUID | None = None,
    member_ids: list[uuid.UUID] | None = None,
) -> Team:
    """Creates a team and adds `member_ids` (deduplicated with `created_by`,
    who is always a member of a team they create). Raises 409 on a name
    collision within the same `cohort_id` — self-formed teams (`cohort_id`
    NULL) never collide by name, there's no scope to dedupe them against.
    """
    team = Team(id=uuid.uuid4(), name=name, cohort_id=cohort_id, created_by=created_by)
    db.add(team)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise HTTPException(409, detail="A team with this name already exists in this cohort")

    members = {created_by, *(member_ids or [])}
    for user_id in members:
        db.add(TeamMember(team_id=team.id, user_id=user_id))
    await db.flush()
    return team


async def join_team(db: AsyncSession, *, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    existing = await db.get(TeamMember, (team_id, user_id))
    if existing is not None:
        return
    db.add(TeamMember(team_id=team_id, user_id=user_id))
    await db.flush()


async def leave_team(db: AsyncSession, *, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
    member = await db.get(TeamMember, (team_id, user_id))
    if member is not None:
        await db.delete(member)
        await db.flush()


async def team_member_ids(db: AsyncSession, *, team_id: uuid.UUID) -> list[uuid.UUID]:
    rows = (await db.execute(
        select(TeamMember.user_id).where(TeamMember.team_id == team_id)
    )).scalars().all()
    return list(rows)


async def teams_for_user(db: AsyncSession, *, user_id: uuid.UUID) -> list[Team]:
    return list((await db.execute(
        select(Team)
        .join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id)
        .order_by(Team.created_at.desc())
    )).scalars().all())
