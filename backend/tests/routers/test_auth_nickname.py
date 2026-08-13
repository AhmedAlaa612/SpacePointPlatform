"""Live Games Phase 2C, 8-1 — nickname assignment at signup and the
POST /auth/me/nickname/reroll endpoint. Redis-free (uses the `client`
fixture).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.instructors.invitation_code import InvitationCode
from app.models.user import User
from app.services.nicknames import assign_nickname


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Nickname Router User", email=f"nickr-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.mark.asyncio
async def test_student_signup_gets_a_nickname_immediately(db, client):
    # Signup is invite-only as of 2026-08-13.
    db.add(InvitationCode(
        id=uuid.uuid4(), code="NICKBATCH", kind="student", is_active=True, max_uses=100, used_count=0,
    ))
    await db.commit()
    resp = await client.post("/auth/signup", json={
        "invite_code": "NICKBATCH",
        "full_name": "New Explorer", "email": f"explorer-{uuid.uuid4().hex[:8]}@example.com", "password": "verypass123",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["user"]["nickname"]


@pytest.mark.asyncio
async def test_me_returns_the_students_nickname(db, client):
    student = await _user(db)
    await assign_nickname(db, student)
    await db.commit()

    resp = await client.get("/auth/me", headers=_headers(student))
    assert resp.status_code == 200
    assert resp.json()["nickname"] == student.nickname


@pytest.mark.asyncio
async def test_reroll_requires_a_student_account(db, client):
    ops = await _user(db, roles=["operations"])
    await db.commit()
    resp = await client.post("/auth/me/nickname/reroll", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_reroll_changes_it_then_rate_limits_a_second_call(db, client):
    student = await _user(db)
    await assign_nickname(db, student)
    original = student.nickname
    await db.commit()

    first = await client.post("/auth/me/nickname/reroll", headers=_headers(student))
    assert first.status_code == 200, first.text
    assert first.json()["nickname"] != original

    second = await client.post("/auth/me/nickname/reroll", headers=_headers(student))
    assert second.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.asyncio
async def test_reroll_works_again_after_the_cooldown(db, client):
    student = await _user(db)
    await assign_nickname(db, student)
    student.nickname_rerolled_at = datetime.now(timezone.utc) - timedelta(days=8)
    await db.commit()

    resp = await client.post("/auth/me/nickname/reroll", headers=_headers(student))
    assert resp.status_code == 200, resp.text
