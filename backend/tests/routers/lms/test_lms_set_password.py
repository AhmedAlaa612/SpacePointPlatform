"""LM1-7 / §8 Q5 — POST /auth/set-password, the "invite sent" link an
ops-created LMS account follows to pick its own password. Token-authenticated
(core/security.py's create/decode_password_set_token), not a logged-in-user
action. Redis-free.
"""

import uuid
from datetime import timedelta

import pytest
from fastapi import status as http_status

from app.core.security import create_password_set_token, verify_password
from app.models.user import User


async def _invited_user(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Invited Student", email=f"invited-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="unusable-random-hash", roles=["student"], status="active", must_change_password=True,
    )
    db.add(user)
    await db.commit()
    return user


@pytest.mark.asyncio
async def test_set_password_with_a_valid_token_clears_must_change_password(db, client):
    user = await _invited_user(db)
    token = create_password_set_token(user.id)

    resp = await client.post("/auth/set-password", json={"token": token, "new_password": "a-new-secret"})
    assert resp.status_code == 200

    await db.refresh(user)
    assert user.must_change_password is False
    assert verify_password("a-new-secret", user.password_hash)

    login = await client.post("/auth/login", json={"email": user.email, "password": "a-new-secret"})
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_set_password_rejects_expired_or_garbage_token(db, client):
    user = await _invited_user(db)
    expired = create_password_set_token(user.id, expires_delta=timedelta(seconds=-1))

    resp = await client.post("/auth/set-password", json={"token": expired, "new_password": "x"})
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST

    garbage = await client.post("/auth/set-password", json={"token": "not-a-token", "new_password": "x"})
    assert garbage.status_code == http_status.HTTP_400_BAD_REQUEST

    await db.refresh(user)
    assert user.must_change_password is True  # untouched
