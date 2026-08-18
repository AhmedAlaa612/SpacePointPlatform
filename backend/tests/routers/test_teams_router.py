"""Team membership routes (2026-08-17) — `/teams/*`. Redis-free (uses the
`client` fixture), mirrors `test_missions_team_formation.py`'s fixture
style for the router-level half of the domain-agnostic team split.
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.user import User
from app.services.teams import create_team, team_member_ids

pytestmark = pytest.mark.asyncio


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Teams Router User", email=f"teamsrouter-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def test_join_team_happy_path(db, client):
    creator = await _user(db)
    joiner = await _user(db)
    team = await create_team(db, name="Router Team A", created_by=creator.id)
    await db.commit()

    resp = await client.post(f"/teams/{team.id}/join", headers=_headers(joiner))
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text
    assert str(joiner.id) in resp.json()["member_ids"]

    member_ids = await team_member_ids(db, team_id=team.id)
    assert joiner.id in member_ids


async def test_join_team_already_a_member_is_409(db, client):
    creator = await _user(db)
    team = await create_team(db, name="Router Team B", created_by=creator.id)
    await db.commit()

    resp = await client.post(f"/teams/{team.id}/join", headers=_headers(creator))
    assert resp.status_code == http_status.HTTP_409_CONFLICT


async def test_join_nonexistent_team_is_404(db, client):
    joiner = await _user(db)
    await db.commit()

    resp = await client.post(f"/teams/{uuid.uuid4()}/join", headers=_headers(joiner))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


async def test_leave_team_reduces_the_roster(db, client):
    creator = await _user(db)
    other = await _user(db)
    team = await create_team(db, name="Router Team C", created_by=creator.id, member_ids=[other.id])
    await db.commit()

    resp = await client.delete(f"/teams/{team.id}/leave", headers=_headers(other))
    assert resp.status_code == http_status.HTTP_204_NO_CONTENT

    member_ids = await team_member_ids(db, team_id=team.id)
    assert other.id not in member_ids
    assert creator.id in member_ids


async def test_leave_team_when_not_a_member_is_404(db, client):
    creator = await _user(db)
    outsider = await _user(db)
    team = await create_team(db, name="Router Team D", created_by=creator.id)
    await db.commit()

    resp = await client.delete(f"/teams/{team.id}/leave", headers=_headers(outsider))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


async def test_member_leaving_does_not_touch_a_started_attempts_frozen_roster(db, client):
    """A live roster change after `start_attempt()` must never rewrite who
    was actually on the hook for that specific attempt's grade."""
    from app.models.missions.mission import Mission, MissionAttemptMember, MissionVariant
    from app.services.missions import start_attempt

    author = await _user(db, roles=["operations"])
    mission = Mission(
        id=uuid.uuid4(), title="Team Attempt Freeze Mission", slug=f"team-freeze-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published", team_policy="team",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Engineer", position=1, points=50)
    db.add(variant)
    await db.flush()

    creator = await _user(db)
    leaver = await _user(db)
    team = await create_team(db, name="Router Team E", created_by=creator.id, member_ids=[leaver.id])
    await db.commit()

    attempt = await start_attempt(db, mission_id=mission.id, variant_id=variant.id, team_id=team.id)
    await db.commit()

    frozen_before = {
        m.user_id for m in (await db.execute(
            select(MissionAttemptMember).where(MissionAttemptMember.attempt_id == attempt.id)
        )).scalars().all()
    }
    assert frozen_before == {creator.id, leaver.id}

    resp = await client.delete(f"/teams/{team.id}/leave", headers=_headers(leaver))
    assert resp.status_code == http_status.HTTP_204_NO_CONTENT

    frozen_after = {
        m.user_id for m in (await db.execute(
            select(MissionAttemptMember).where(MissionAttemptMember.attempt_id == attempt.id)
        )).scalars().all()
    }
    assert frozen_after == frozen_before  # unchanged despite the live roster losing a member
