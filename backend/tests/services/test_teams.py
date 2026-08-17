"""Team primitives (2026-08-17) — relocated from
`tests/services/missions/test_missions_teams.py` now that `Team` is a
domain-agnostic entity (`app/services/teams.py`), not missions-only.
Redis-free, HTTP-free.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User
from app.services.teams import create_team, join_team, leave_team, team_member_ids, teams_for_user


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Team User", email=f"team-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=roles or ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"TP-{uuid.uuid4().hex[:8]}", name="Team Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Team Cohort", status="running")
    db.add(cohort)
    await db.flush()
    return cohort


@pytest.mark.asyncio
async def test_create_team_adds_creator_as_a_member(db):
    creator = await _user(db, roles=["operations"])
    team = await create_team(db, name="Team Alpha", created_by=creator.id)
    assert await team_member_ids(db, team_id=team.id) == [creator.id]


@pytest.mark.asyncio
async def test_create_team_adds_all_specified_members_deduplicated_with_creator(db):
    creator = await _user(db)
    other = await _user(db)
    team = await create_team(db, name="Team Bravo", created_by=creator.id, member_ids=[creator.id, other.id])
    members = set(await team_member_ids(db, team_id=team.id))
    assert members == {creator.id, other.id}


@pytest.mark.asyncio
async def test_duplicate_name_within_the_same_cohort_is_rejected(db):
    creator = await _user(db)
    cohort = await _cohort(db)
    await create_team(db, name="Team Alpha", created_by=creator.id, cohort_id=cohort.id)
    with pytest.raises(HTTPException) as exc:
        await create_team(db, name="Team Alpha", created_by=creator.id, cohort_id=cohort.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_same_name_is_fine_across_different_cohorts(db):
    creator = await _user(db)
    cohort_a = await _cohort(db)
    cohort_b = await _cohort(db)
    a = await create_team(db, name="Team Alpha", created_by=creator.id, cohort_id=cohort_a.id)
    b = await create_team(db, name="Team Alpha", created_by=creator.id, cohort_id=cohort_b.id)
    assert a.id != b.id


@pytest.mark.asyncio
async def test_self_formed_teams_are_never_deduplicated_by_name(db):
    creator = await _user(db)
    a = await create_team(db, name="Team Alpha", created_by=creator.id, cohort_id=None)
    b = await create_team(db, name="Team Alpha", created_by=creator.id, cohort_id=None)
    assert a.id != b.id


@pytest.mark.asyncio
async def test_join_and_leave_team(db):
    creator = await _user(db)
    other = await _user(db)
    team = await create_team(db, name="Team Charlie", created_by=creator.id)

    await join_team(db, team_id=team.id, user_id=other.id)
    assert set(await team_member_ids(db, team_id=team.id)) == {creator.id, other.id}

    await leave_team(db, team_id=team.id, user_id=other.id)
    assert await team_member_ids(db, team_id=team.id) == [creator.id]


@pytest.mark.asyncio
async def test_joining_an_existing_member_twice_is_a_noop(db):
    creator = await _user(db)
    team = await create_team(db, name="Team Delta", created_by=creator.id)
    await join_team(db, team_id=team.id, user_id=creator.id)  # already a member
    assert await team_member_ids(db, team_id=team.id) == [creator.id]


@pytest.mark.asyncio
async def test_leaving_a_team_you_are_not_on_is_a_noop(db):
    creator = await _user(db)
    other = await _user(db)
    team = await create_team(db, name="Team Golf", created_by=creator.id)
    await leave_team(db, team_id=team.id, user_id=other.id)  # never joined
    assert await team_member_ids(db, team_id=team.id) == [creator.id]


@pytest.mark.asyncio
async def test_teams_for_user_lists_every_team_a_user_belongs_to(db):
    creator = await _user(db)
    other = await _user(db)
    team_a = await create_team(db, name="Team Echo", created_by=creator.id)
    team_b = await create_team(db, name="Team Foxtrot", created_by=other.id, member_ids=[creator.id])

    teams = await teams_for_user(db, user_id=creator.id)
    assert {t.id for t in teams} == {team_a.id, team_b.id}
