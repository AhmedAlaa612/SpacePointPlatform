"""P6-2 (LMS Phase 2 Stage 6, 2026-08-11) — team-scoped attempts: the
user_id XOR team_id start_attempt path and the MissionAttemptMember
snapshot. Redis-free, HTTP-free.
"""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.models.missions.mission import Mission, MissionAttempt, MissionAttemptMember, MissionVariant
from app.models.user import User
from app.services.missions import start_attempt
from app.services.teams import create_team, join_team, leave_team


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Team Attempt User", email=f"ta-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=roles or ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _mission_with_variant(db, *, author) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Team Mission", slug=f"team-mission-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published", team_policy="team",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=40)
    db.add(variant)
    await db.flush()
    return mission, variant


@pytest.mark.asyncio
async def test_start_attempt_requires_exactly_one_of_user_or_team(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission_with_variant(db, author=author)
    student = await _user(db)
    team = await create_team(db, name="Solo XOR Team", created_by=student.id)

    with pytest.raises(HTTPException):
        await start_attempt(db, mission_id=mission.id, variant_id=variant.id)  # neither

    with pytest.raises(HTTPException):
        await start_attempt(
            db, mission_id=mission.id, variant_id=variant.id, user_id=student.id, team_id=team.id,
        )  # both


@pytest.mark.asyncio
async def test_team_attempt_snapshots_current_roster(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission_with_variant(db, author=author)
    alice = await _user(db)
    bob = await _user(db)
    team = await create_team(db, name="Snapshot Team", created_by=alice.id, member_ids=[bob.id])

    attempt = await start_attempt(db, mission_id=mission.id, variant_id=variant.id, team_id=team.id)
    assert attempt.user_id is None
    assert attempt.team_id == team.id

    from sqlalchemy import select
    snapshot = (await db.execute(
        select(MissionAttemptMember.user_id).where(MissionAttemptMember.attempt_id == attempt.id)
    )).scalars().all()
    assert set(snapshot) == {alice.id, bob.id}


@pytest.mark.asyncio
async def test_changing_the_team_after_starting_does_not_change_the_snapshot(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission_with_variant(db, author=author)
    alice = await _user(db)
    bob = await _user(db)
    carol = await _user(db)
    team = await create_team(db, name="Roster Change Team", created_by=alice.id, member_ids=[bob.id])

    attempt = await start_attempt(db, mission_id=mission.id, variant_id=variant.id, team_id=team.id)

    # Roster changes after the attempt started.
    await leave_team(db, team_id=team.id, user_id=bob.id)
    await join_team(db, team_id=team.id, user_id=carol.id)

    from sqlalchemy import select
    snapshot = (await db.execute(
        select(MissionAttemptMember.user_id).where(MissionAttemptMember.attempt_id == attempt.id)
    )).scalars().all()
    assert set(snapshot) == {alice.id, bob.id}  # frozen at start — carol never appears, bob still does


@pytest.mark.asyncio
async def test_team_attempt_is_single_flight_per_team(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission_with_variant(db, author=author)
    alice = await _user(db)
    team = await create_team(db, name="Single Flight Team", created_by=alice.id)

    first = await start_attempt(db, mission_id=mission.id, variant_id=variant.id, team_id=team.id)
    second = await start_attempt(db, mission_id=mission.id, variant_id=variant.id, team_id=team.id)
    assert first.id == second.id


@pytest.mark.asyncio
async def test_solo_and_team_attempts_number_independently(db):
    """attempt_no is scoped per owner — a user's solo attempts and a team's
    attempts on the same mission don't share a counter."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission_with_variant(db, author=author)
    alice = await _user(db)
    team = await create_team(db, name="Independent Numbering Team", created_by=alice.id)

    solo = await start_attempt(db, mission_id=mission.id, variant_id=variant.id, user_id=alice.id)
    team_attempt = await start_attempt(db, mission_id=mission.id, variant_id=variant.id, team_id=team.id)
    assert solo.attempt_no == 1
    assert team_attempt.attempt_no == 1


@pytest.mark.asyncio
async def test_db_check_constraint_rejects_neither_and_both(db):
    """Belt-and-suspenders: the service layer validates, but the DB CHECK
    is the real guarantee if some future code path bypasses the service."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _mission_with_variant(db, author=author)

    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(MissionAttempt(
                id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, attempt_no=99,
                user_id=None, team_id=None,
            ))
            await db.flush()
