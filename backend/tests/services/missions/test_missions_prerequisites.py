"""P5-6 (LMS Phase 2 Stage 5, 2026-08-11) — prerequisite DAG evaluation.
Redis-free, HTTP-free.
"""

import uuid

import pytest

from app.models.missions.mission import Mission, MissionPrerequisite, MissionVariant
from app.models.user import User
from app.services.missions import decide_attempt, is_unlocked, prerequisite_status, start_attempt


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Prereq User", email=f"prereq-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=roles or ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _mission(db, *, author, title="Mission") -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title=title, slug=f"{title.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=20)
    db.add(variant)
    await db.flush()
    return mission, variant


@pytest.mark.asyncio
async def test_a_mission_with_no_prerequisites_is_always_unlocked(db):
    author = await _user(db, roles=["operations"])
    mission, _ = await _mission(db, author=author)
    student = await _user(db)
    assert await is_unlocked(db, mission_id=mission.id, user_id=student.id) is True
    assert await prerequisite_status(db, mission_id=mission.id, user_id=student.id) == []


@pytest.mark.asyncio
async def test_locked_until_the_prerequisite_is_passed(db):
    author = await _user(db, roles=["operations"])
    basic, basic_variant = await _mission(db, author=author, title="Basic Radio")
    advanced, _ = await _mission(db, author=author, title="Advanced Radio")
    db.add(MissionPrerequisite(mission_id=advanced.id, requires_mission_id=basic.id))
    await db.flush()
    student = await _user(db)

    assert await is_unlocked(db, mission_id=advanced.id, user_id=student.id) is False
    status = await prerequisite_status(db, mission_id=advanced.id, user_id=student.id)
    assert status == [{"mission_id": basic.id, "title": "Basic Radio", "satisfied": False}]

    attempt = await start_attempt(db, user_id=student.id, mission_id=basic.id, variant_id=basic_variant.id)
    await decide_attempt(db, attempt=attempt, passed=True, score=90)

    assert await is_unlocked(db, mission_id=advanced.id, user_id=student.id) is True
    status_after = await prerequisite_status(db, mission_id=advanced.id, user_id=student.id)
    assert status_after == [{"mission_id": basic.id, "title": "Basic Radio", "satisfied": True}]


@pytest.mark.asyncio
async def test_failing_the_prerequisite_does_not_unlock(db):
    author = await _user(db, roles=["operations"])
    basic, basic_variant = await _mission(db, author=author, title="Basic Wiring")
    advanced, _ = await _mission(db, author=author, title="Advanced Wiring")
    db.add(MissionPrerequisite(mission_id=advanced.id, requires_mission_id=basic.id))
    await db.flush()
    student = await _user(db)

    attempt = await start_attempt(db, user_id=student.id, mission_id=basic.id, variant_id=basic_variant.id)
    await decide_attempt(db, attempt=attempt, passed=False)

    assert await is_unlocked(db, mission_id=advanced.id, user_id=student.id) is False


@pytest.mark.asyncio
async def test_multiple_prerequisites_all_must_be_satisfied(db):
    author = await _user(db, roles=["operations"])
    a, a_variant = await _mission(db, author=author, title="Mission A")
    b, b_variant = await _mission(db, author=author, title="Mission B")
    c, _ = await _mission(db, author=author, title="Mission C")
    db.add_all([
        MissionPrerequisite(mission_id=c.id, requires_mission_id=a.id),
        MissionPrerequisite(mission_id=c.id, requires_mission_id=b.id),
    ])
    await db.flush()
    student = await _user(db)

    attempt_a = await start_attempt(db, user_id=student.id, mission_id=a.id, variant_id=a_variant.id)
    await decide_attempt(db, attempt=attempt_a, passed=True, score=90)
    assert await is_unlocked(db, mission_id=c.id, user_id=student.id) is False  # B still missing

    attempt_b = await start_attempt(db, user_id=student.id, mission_id=b.id, variant_id=b_variant.id)
    await decide_attempt(db, attempt=attempt_b, passed=True, score=90)
    assert await is_unlocked(db, mission_id=c.id, user_id=student.id) is True


@pytest.mark.asyncio
async def test_passing_any_variant_satisfies_the_prerequisite(db):
    """Readiness is per-mission, not per-difficulty — passing the easy
    variant of a prerequisite is enough to unlock what depends on it."""
    author = await _user(db, roles=["operations"])
    basic, basic_variant = await _mission(db, author=author, title="Either Variant Basic")
    hard_variant = MissionVariant(id=uuid.uuid4(), mission_id=basic.id, label="Hard", position=2, points=50)
    db.add(hard_variant)
    advanced, _ = await _mission(db, author=author, title="Either Variant Advanced")
    db.add(MissionPrerequisite(mission_id=advanced.id, requires_mission_id=basic.id))
    await db.flush()
    student = await _user(db)

    attempt = await start_attempt(db, user_id=student.id, mission_id=basic.id, variant_id=basic_variant.id)
    await decide_attempt(db, attempt=attempt, passed=True, score=90)

    assert await is_unlocked(db, mission_id=advanced.id, user_id=student.id) is True
