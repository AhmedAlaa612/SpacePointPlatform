"""Step 1 — SpacePoint Website Global Config & Live Counters.

Public GET /public/website/config is unauthenticated; admin GET/PUT
/admin/website/config require the admin role. Updating the instructor
invite code must be immediately visible on the public endpoint (the
marketing site reads it with no redeploy).
"""

import uuid

import pytest
from sqlalchemy import delete

from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.website_config import WebsiteConfig


async def _ensure_table(db):
    conn = await db.connection()
    await conn.run_sync(lambda c: WebsiteConfig.__table__.create(c, checkfirst=True))


async def _make_user(db, roles):
    user = User(
        id=uuid.uuid4(),
        full_name="Test User",
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("pass"),
        roles=roles,
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.roles)}"}


@pytest.mark.asyncio
async def test_public_config_returns_defaults_unauthenticated(db, client):
    await _ensure_table(db)
    await db.execute(delete(WebsiteConfig))
    await db.flush()

    resp = await client.get("/public/website/config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["students_count"] == "2,700+"
    assert body["workshops_count"] == "40+"
    assert body["partners_count"] == "25"
    assert body["satellites_flown_count"] == "50+"
    assert body["instructor_invite_code"] == "UOWD26"
    assert body["intern_invite_code"] == "UOWD26"
    assert body["contact_email"] == "info@spacepoint.ae"


@pytest.mark.asyncio
async def test_admin_config_requires_admin_or_operations(db, client):
    await _ensure_table(db)
    await db.execute(delete(WebsiteConfig))
    await db.flush()

    # No token at all
    assert (await client.get("/admin/website/config")).status_code in (401, 403)
    assert (await client.put("/admin/website/config", json={"students_count": "9"})).status_code in (401, 403)

    # Non-admin/ops token is forbidden
    student = await _make_user(db, ["student"])
    resp = await client.get("/admin/website/config", headers=_headers(student))
    assert resp.status_code == 403
    resp = await client.put("/admin/website/config", json={"students_count": "9"}, headers=_headers(student))
    assert resp.status_code == 403

    # Operations role can read and update
    ops = await _make_user(db, ["operations"])
    resp = await client.get("/admin/website/config", headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    resp = await client.put("/admin/website/config", json={"students_count": "3,000+"}, headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    assert resp.json()["students_count"] == "3,000+"


@pytest.mark.asyncio
async def test_admin_update_reflects_immediately_on_public(db, client):
    """The task's verification scenario: set instructor code to TEST123 in
    the portal and the public apply-link source updates at once."""
    await _ensure_table(db)
    await db.execute(delete(WebsiteConfig))
    await db.flush()

    admin = await _make_user(db, ["admin"])

    resp = await client.get("/admin/website/config", headers=_headers(admin))
    assert resp.status_code == 200, resp.text

    resp = await client.put(
        "/admin/website/config",
        json={"instructor_invite_code": "TEST123"},
        headers=_headers(admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["instructor_invite_code"] == "TEST123"

    public = await client.get("/public/website/config")
    assert public.status_code == 200, public.text
    assert public.json()["instructor_invite_code"] == "TEST123"

    # Clearing the code is how the site falls back to the bare /apply/* link
    resp = await client.put(
        "/admin/website/config",
        json={"instructor_invite_code": None},
        headers=_headers(admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["instructor_invite_code"] is None
