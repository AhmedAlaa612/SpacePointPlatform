"""B6 — /auth/login gets a per-account lockout (the existing rate_limit.py
brake is 1000 req/min/IP, deliberately generous for shared-venue WiFi, and
useless against password guessing) and /auth/signup gets the same per-IP
brake the public registration form already has. Redis-free.
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import get_password_hash
from app.models.user import User
from app.routers import auth as auth_router


async def _user(db, *, password="correct-horse") -> User:
    user = User(
        id=uuid.uuid4(), full_name="Lockout Test User", email=f"lockout-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash(password), roles=["student"], status="active",
    )
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_login_locks_after_max_failed_attempts_then_rejects_the_correct_password(db, client):
    user = await _user(db, password="the-real-password")

    for _ in range(auth_router._MAX_FAILED_LOGIN_ATTEMPTS):
        resp = await client.post("/auth/login", json={"email": user.email, "password": "wrong"})
        assert resp.status_code == http_status.HTTP_401_UNAUTHORIZED

    await db.refresh(user)
    assert user.failed_login_count == auth_router._MAX_FAILED_LOGIN_ATTEMPTS
    assert user.locked_until is not None

    # Locked out now — even the *correct* password is rejected, with 429 not 401.
    locked = await client.post("/auth/login", json={"email": user.email, "password": "the-real-password"})
    assert locked.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.asyncio
async def test_successful_login_resets_the_failed_attempt_counter(db, client):
    user = await _user(db, password="the-real-password")

    for _ in range(3):
        resp = await client.post("/auth/login", json={"email": user.email, "password": "wrong"})
        assert resp.status_code == http_status.HTTP_401_UNAUTHORIZED
    await db.refresh(user)
    assert user.failed_login_count == 3

    ok = await client.post("/auth/login", json={"email": user.email, "password": "the-real-password"})
    assert ok.status_code == 200, ok.text

    await db.refresh(user)
    assert user.failed_login_count == 0
    assert user.locked_until is None


@pytest.mark.asyncio
async def test_a_wrong_password_for_an_unknown_email_never_raises(db, client):
    """No account row to attach a counter to — must fall back to the
    existing flat 401, never a 500 from touching a None user."""
    resp = await client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert resp.status_code == http_status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_signup_is_rate_limited_the_same_way_the_public_form_is(db, client, monkeypatch):
    """Proves the wiring, not the limiter itself (already exhaustively
    covered in tests/core/test_rate_limit.py) — the same pattern this
    codebase uses for public_register (routers/sessions/public.py)."""
    def _always_trips(request, **kwargs):
        from fastapi import HTTPException
        raise HTTPException(http_status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests — try again shortly")

    monkeypatch.setattr(auth_router, "enforce_rate_limit", _always_trips)

    resp = await client.post("/auth/signup", json={
        "full_name": "Rate Limited", "email": "ratelimited@example.com", "password": "pass-ratelimited",
    })
    assert resp.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS

    user = (await db.execute(
        select(User).where(User.email == "ratelimited@example.com")
    )).scalars().first()
    assert user is None
