"""Step 7 — SpacePoint Labs R&D projects.

Public GET /public/labs/projects is unauthenticated (active only,
ordered); admin CRUD requires the admin role.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.website_labs import WebsiteLabProject


async def _ensure_table(db):
    conn = await db.connection()
    await conn.run_sync(lambda c: WebsiteLabProject.__table__.create(c, checkfirst=True))


async def _clear(db):
    await db.execute(delete(WebsiteLabProject))
    await db.flush()


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
async def test_labs_public_lists_active_ordered(db, client):
    await _ensure_table(db)
    await _clear(db)

    assert (await client.get("/public/labs/projects")).json() == []

    admin = await _make_user(db, ["admin"])
    first = await client.post(
        "/admin/website/labs",
        json={"title": "Beta Project", "description": "Second.", "display_order": 2},
        headers=_headers(admin),
    )
    assert first.status_code == 201, first.text
    assert first.json()["slug"] == "beta-project"
    second = await client.post(
        "/admin/website/labs",
        json={"title": "Alpha Project", "description": "First.", "display_order": 1},
        headers=_headers(admin),
    )
    assert second.status_code == 201, second.text

    public = (await client.get("/public/labs/projects")).json()
    assert [p["slug"] for p in public] == ["alpha-project", "beta-project"]

    # Unpublish hides from public but stays in admin
    await client.put(
        f"/admin/website/labs/{first.json()['id']}",
        json={"is_active": False},
        headers=_headers(admin),
    )
    assert len((await client.get("/public/labs/projects")).json()) == 1
    assert len((await client.get("/admin/website/labs", headers=_headers(admin))).json()) == 2


@pytest.mark.asyncio
async def test_labs_admin_guards_and_crud(db, client):
    await _ensure_table(db)
    await _clear(db)
    admin = await _make_user(db, ["admin"])
    student = await _make_user(db, ["student"])

    assert (await client.get("/admin/website/labs")).status_code in (401, 403)
    assert (
        await client.post("/admin/website/labs", json={"title": "X", "description": "Y"})
    ).status_code in (401, 403)
    assert (await client.get("/admin/website/labs", headers=_headers(student))).status_code == 403

    ops = await _make_user(db, ["operations"])
    assert (await client.get("/admin/website/labs", headers=_headers(ops))).status_code == 200

    created = (
        await client.post(
            "/admin/website/labs",
            json={
                "title": "Miura-Ori Solar Array",
                "description": "Origami arrays.",
                "badges": ["Active Simulation"],
            },
            headers=_headers(admin),
        )
    ).json()
    assert created["badges"] == ["Active Simulation"]
    assert created["project_url"] == "/miura-ori"

    updated = (
        await client.put(
            f"/admin/website/labs/{created['id']}",
            json={"cta_label": "Open Simulation"},
            headers=_headers(admin),
        )
    ).json()
    assert updated["cta_label"] == "Open Simulation"

    assert (
        await client.put(
            f"/admin/website/labs/{uuid.uuid4()}", json={"title": "Ghost"}, headers=_headers(admin)
        )
    ).status_code == 404

    assert (
        await client.delete(f"/admin/website/labs/{created['id']}", headers=_headers(admin))
    ).status_code == 204
    assert (await client.get("/public/labs/projects")).json() == []
