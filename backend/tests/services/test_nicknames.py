"""Live Games Phase 2C, 8-1 (D1, D2) — nickname generation and the
7-day reroll cooldown. Redis-free, HTTP-free.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.user import User
from app.services.nicknames import CREATURE_WORDS, COSMIC_WORDS, assign_nickname, reroll_nickname


async def _student(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Nickname Student", email=f"nick-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_assign_nickname_sets_a_well_formed_unique_value(db):
    student = await _student(db)
    assert student.nickname is None

    await assign_nickname(db, student)

    assert student.nickname is not None
    # cosmic + creature + 3-digit number, no separator
    matched = [
        (c, r) for c in COSMIC_WORDS for r in CREATURE_WORDS
        if student.nickname.startswith(c) and student.nickname[len(c):].startswith(r)
    ]
    assert matched, f"{student.nickname!r} doesn't decompose into a known cosmic+creature pair"
    suffix = student.nickname[len(matched[0][0]) + len(matched[0][1]):]
    assert suffix.isdigit() and len(suffix) == 3


@pytest.mark.asyncio
async def test_assign_nickname_is_idempotent(db):
    student = await _student(db)
    await assign_nickname(db, student)
    first = student.nickname

    await assign_nickname(db, student)

    assert student.nickname == first


@pytest.mark.asyncio
async def test_two_students_never_collide(db):
    a = await _student(db)
    b = await _student(db)
    await assign_nickname(db, a)
    await assign_nickname(db, b)
    assert a.nickname != b.nickname


@pytest.mark.asyncio
async def test_reroll_changes_the_nickname_and_stamps_the_cooldown(db):
    student = await _student(db)
    await assign_nickname(db, student)
    original = student.nickname
    assert student.nickname_rerolled_at is None

    new_nickname = await reroll_nickname(db, student)

    assert new_nickname != original
    assert student.nickname == new_nickname
    assert student.nickname_rerolled_at is not None


@pytest.mark.asyncio
async def test_reroll_is_rate_limited_to_once_a_week(db):
    student = await _student(db)
    await assign_nickname(db, student)
    await reroll_nickname(db, student)

    with pytest.raises(HTTPException) as e:
        await reroll_nickname(db, student)
    assert e.value.status_code == 429


@pytest.mark.asyncio
async def test_reroll_is_allowed_again_once_the_cooldown_passes(db):
    student = await _student(db)
    await assign_nickname(db, student)
    student.nickname_rerolled_at = datetime.now(timezone.utc) - timedelta(days=8)
    await db.flush()

    # should not raise
    new_nickname = await reroll_nickname(db, student)
    assert new_nickname == student.nickname
