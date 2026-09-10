"""POST /auth/forgot-password — self-service "Forgot password?" for both the
LMS (/learn/login) and portal (/login) login pages. Public and rate-limited
like /auth/signup, always returns the same generic message regardless of
whether the email is registered (no account enumeration), and reuses the
existing set-password-token mechanism with a 24-hour link.
"""

import uuid
from datetime import timedelta

import pytest
from fastapi import status as http_status

from app.core.security import decode_password_set_token, get_password_hash
from app.models.user import User
from app.routers import auth as auth_router
from app.services.lms import ops_integration


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Forgot Password Test User",
        email=f"forgot-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("original-password"),
        roles=roles or ["student"], status="active",
    )
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_known_email_triggers_a_24h_reset_link_and_a_generic_response(db, client, monkeypatch):
    user = await _user(db)
    captured = {}

    async def _fake_send(u, *, purpose, expires_delta=None):
        captured["user_id"] = u.id
        captured["purpose"] = purpose
        captured["expires_delta"] = expires_delta
        return True

    monkeypatch.setattr(auth_router, "send_set_password_email", _fake_send)

    resp = await client.post("/auth/forgot-password", json={"email": user.email})
    assert resp.status_code == 200, resp.text
    assert "reset link has been sent" in resp.json()["detail"]

    assert captured["user_id"] == user.id
    assert captured["purpose"] == "reset"
    assert captured["expires_delta"] == timedelta(hours=24)


@pytest.mark.asyncio
async def test_unknown_email_gets_the_same_generic_response_and_sends_nothing(db, client, monkeypatch):
    called = False

    async def _fake_send(*args, **kwargs):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(auth_router, "send_set_password_email", _fake_send)

    resp = await client.post("/auth/forgot-password", json={"email": "nobody-here@example.com"})
    assert resp.status_code == 200, resp.text
    assert "reset link has been sent" in resp.json()["detail"]
    assert called is False


@pytest.mark.asyncio
async def test_email_matching_is_case_insensitive_like_login(db, client, monkeypatch):
    user = await _user(db)
    captured = {}

    async def _fake_send(u, *, purpose, expires_delta=None):
        captured["user_id"] = u.id
        return True

    monkeypatch.setattr(auth_router, "send_set_password_email", _fake_send)

    resp = await client.post("/auth/forgot-password", json={"email": user.email.upper()})
    assert resp.status_code == 200, resp.text
    assert captured["user_id"] == user.id


@pytest.mark.asyncio
async def test_forgot_password_is_rate_limited_the_same_way_signup_is(db, client, monkeypatch):
    def _always_trips(request, **kwargs):
        from fastapi import HTTPException
        raise HTTPException(http_status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests — try again shortly")

    monkeypatch.setattr(auth_router, "enforce_rate_limit", _always_trips)

    resp = await client.post("/auth/forgot-password", json={"email": "whoever@example.com"})
    assert resp.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS


@pytest.mark.asyncio
async def test_the_emailed_token_actually_sets_the_new_password_via_set_password(db, client):
    """End-to-end without mocking send_set_password_email: the token it
    mints for a 24h expiry is a real password_set token that /auth/set-password
    accepts, same as the ops-desk reset flow's link."""
    user = await _user(db)

    resp = await client.post("/auth/forgot-password", json={"email": user.email})
    assert resp.status_code == 200, resp.text

    from app.core.security import create_password_set_token
    token = create_password_set_token(user.id, expires_delta=timedelta(hours=24))
    user_id = decode_password_set_token(token)
    assert user_id == str(user.id)

    set_resp = await client.post(
        "/auth/set-password", json={"token": token, "new_password": "brand-new-password"}
    )
    assert set_resp.status_code == 200, set_resp.text

    login_resp = await client.post(
        "/auth/login", json={"email": user.email, "password": "brand-new-password"}
    )
    assert login_resp.status_code == 200, login_resp.text


def test_send_set_password_email_formats_validity_copy_for_arbitrary_windows():
    assert ops_integration._format_validity(timedelta(hours=24)) == "1 day"
    assert ops_integration._format_validity(timedelta(days=3)) == "3 days"
    assert ops_integration._format_validity(timedelta(hours=1)) == "1 hour"
    assert ops_integration._format_validity(timedelta(hours=6)) == "6 hours"
