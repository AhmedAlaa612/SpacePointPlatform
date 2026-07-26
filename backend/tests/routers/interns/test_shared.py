"""Tests for routers/interns/shared.py's self-service PATCH /users/me
(2026-07-24) — regression coverage for a latent bug flagged during review of
services/user.py's role-history wiring (see tests/services/test_user.py's
test_role_history_guard_ignores_bare_none_roles): the handler used to do
`user_in.roles = None` as a defensive guard against a client smuggling role
changes through profile self-edit, but Pydantic v2 marks an attribute
assignment as "set" in model_fields_set — so `.dict(exclude_unset=True)`
included `"roles": None`, which services/user.py::update_user then assigned
onto the NOT NULL users.roles column via setattr, raising IntegrityError on
commit. Fixed by giving self-service a narrower schema (UserSelfUpdate) that
has no `roles` field at all, instead of nulling it out after construction.
"""

import uuid

import httpx
import pytest

from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.enums import UserRole
from app.models.user import User


@pytest.fixture
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_user(db, roles: list[UserRole], **overrides) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        full_name="Test User",
        email=f"{uuid.uuid4().hex}@example.com",
        password_hash=get_password_hash("password123"),
        roles=roles,
        status="active",
    )
    defaults.update(overrides)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token(user.id, user.role_values)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_patch_users_me_updates_profile_and_preserves_roles(db, client):
    user = await _make_user(db, [UserRole.intern])

    resp = await client.patch(
        "/interns/users/me",
        json={"full_name": "Updated Name", "phone": "+971500000000"},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["full_name"] == "Updated Name"
    assert body["phone"] == "+971500000000"
    assert body["roles"] == ["intern"]

    await db.refresh(user)
    assert user.full_name == "Updated Name"
    assert user.role_values == ["intern"]


@pytest.mark.asyncio
async def test_patch_users_me_cannot_smuggle_role_change(db, client):
    """A client-supplied `roles` field must be silently ignored, not applied
    and not cause a 500 (the original bug: nulling it server-side after
    construction still landed a NOT NULL violation on commit)."""
    user = await _make_user(db, [UserRole.intern])

    resp = await client.patch(
        "/interns/users/me",
        json={"full_name": "Still Me", "roles": ["admin"]},
        headers=_auth_headers(user),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["roles"] == ["intern"]

    await db.refresh(user)
    assert user.role_values == ["intern"]
