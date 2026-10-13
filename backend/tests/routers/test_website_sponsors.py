"""Step 3 — Partners, Clients & Industry Leaders Showcase.

Public GET /public/sponsors is unauthenticated (grouped by tier by
default, flat list with ?grouped=false) and hides inactive sponsors;
admin GET/POST/PUT/DELETE /admin/website/sponsors/* require the admin
role. Admin edits must be immediately visible on the public endpoint.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.website_sponsor import WebsiteSponsor

SEEDS = [
    {
        "name": "Dubai Future Foundation",
        "logo_url": "/assets/img/dff.png",
        "website_url": "https://dubaifuture.ae",
        "tier": "client",
        "display_order": 1,
        "is_active": True,
    },
    {
        "name": "MBRSC",
        "logo_url": "/assets/img/mbrsc.png",
        "website_url": "https://mbrsc.ae",
        "tier": "client",
        "display_order": 2,
        "is_active": True,
    },
    {
        "name": "EDGE Group",
        "logo_url": "/assets/img/edge.png",
        "website_url": "https://edgegroup.ae",
        "tier": "partner",
        "display_order": 3,
        "is_active": True,
    },
    {
        "name": "UAE Space Agency",
        "logo_url": "/assets/img/uae-space-agency.png",
        "website_url": "https://space.gov.ae",
        "tier": "industry_leader",
        "display_order": 4,
        "is_active": True,
    },
    {
        "name": "Khalifa University",
        "logo_url": "/assets/img/ku.png",
        "website_url": "https://ku.ac.ae",
        "tier": "academic",
        "display_order": 5,
        "is_active": True,
    },
    {
        "name": "University of Sharjah",
        "logo_url": "/assets/img/uos.png",
        "website_url": "https://sharjah.ac.ae",
        "tier": "academic",
        "display_order": 6,
        "is_active": True,
    },
]


async def _ensure_table(db):
    conn = await db.connection()
    await conn.run_sync(lambda c: WebsiteSponsor.__table__.create(c, checkfirst=True))


async def _seed(db):
    await db.execute(delete(WebsiteSponsor))
    await db.flush()
    for seed in SEEDS:
        db.add(WebsiteSponsor(id=uuid.uuid4(), **seed))
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
async def test_public_sponsors_grouped_unauthenticated(db, client):
    await _ensure_table(db)
    await _seed(db)

    resp = await client.get("/public/sponsors")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [s["name"] for s in body["clients"]] == ["Dubai Future Foundation", "MBRSC"]
    assert [s["name"] for s in body["partners"]] == ["EDGE Group"]
    assert body["supporters"] == []
    assert [s["name"] for s in body["academic"]] == ["Khalifa University", "University of Sharjah"]
    assert [s["name"] for s in body["industry_leaders"]] == ["UAE Space Agency"]


@pytest.mark.asyncio
async def test_public_sponsors_flat_list_ordered(db, client):
    await _ensure_table(db)
    await _seed(db)

    resp = await client.get("/public/sponsors", params={"grouped": "false"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list)
    assert [s["display_order"] for s in body] == [1, 2, 3, 4, 5, 6]


@pytest.mark.asyncio
async def test_inactive_hidden_from_public_but_visible_to_admin(db, client):
    await _ensure_table(db)
    await _seed(db)
    admin = await _make_user(db, ["admin"])

    sponsors = (await client.get("/admin/website/sponsors", headers=_headers(admin))).json()
    target = next(s for s in sponsors if s["name"] == "EDGE Group")
    resp = await client.put(
        f"/admin/website/sponsors/{target['id']}",
        json={"is_active": False},
        headers=_headers(admin),
    )
    assert resp.status_code == 200, resp.text

    public = (await client.get("/public/sponsors")).json()
    assert public["partners"] == []
    admin_list = (await client.get("/admin/website/sponsors", headers=_headers(admin))).json()
    assert len(admin_list) == 6


@pytest.mark.asyncio
async def test_admin_sponsors_require_admin(db, client):
    await _ensure_table(db)
    await _seed(db)

    assert (await client.get("/admin/website/sponsors")).status_code in (401, 403)
    assert (
        await client.post("/admin/website/sponsors", json={"name": "X", "logo_url": "/x.png"})
    ).status_code in (401, 403)
    sponsors = (await client.get("/public/sponsors", params={"grouped": "false"})).json()
    assert (
        await client.put(f"/admin/website/sponsors/{sponsors[0]['id']}", json={"name": "Y"})
    ).status_code in (401, 403)
    assert (await client.delete(f"/admin/website/sponsors/{sponsors[0]['id']}")).status_code in (401, 403)

    student = await _make_user(db, ["student"])
    assert (await client.get("/admin/website/sponsors", headers=_headers(student))).status_code == 403
    assert (
        await client.post(
            "/admin/website/sponsors",
            json={"name": "X", "logo_url": "/x.png"},
            headers=_headers(student),
        )
    ).status_code == 403

    ops = await _make_user(db, ["operations"])
    assert (await client.get("/admin/website/sponsors", headers=_headers(ops))).status_code == 200
    assert (
        await client.post(
            "/admin/website/sponsors",
            json={"name": "Ops Partner", "logo_url": "/ops.png"},
            headers=_headers(ops),
        )
    ).status_code == 201


@pytest.mark.asyncio
async def test_admin_post_put_delete_flow_reflects_on_public(db, client):
    await _ensure_table(db)
    await _seed(db)
    admin = await _make_user(db, ["admin"])

    # POST
    resp = await client.post(
        "/admin/website/sponsors",
        json={
            "name": "Test Academy",
            "logo_url": "/assets/img/test.png",
            "website_url": "https://example.com",
            "tier": "academic",
            "display_order": 0,
        },
        headers=_headers(admin),
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["tier"] == "academic"
    assert created["is_active"] is True

    public = (await client.get("/public/sponsors")).json()
    assert [s["name"] for s in public["academic"]][0] == "Test Academy"

    # Invalid tier is rejected
    resp = await client.post(
        "/admin/website/sponsors",
        json={"name": "Bad", "logo_url": "/bad.png", "tier": "platinum"},
        headers=_headers(admin),
    )
    assert resp.status_code == 422

    # PUT
    resp = await client.put(
        f"/admin/website/sponsors/{created['id']}",
        json={"name": "Test Academy Renamed", "display_order": 99},
        headers=_headers(admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Test Academy Renamed"

    # Unknown id is a 404, not a 500
    resp = await client.put(
        f"/admin/website/sponsors/{uuid.uuid4()}",
        json={"name": "Ghost"},
        headers=_headers(admin),
    )
    assert resp.status_code == 404
    assert (await client.delete(f"/admin/website/sponsors/{uuid.uuid4()}", headers=_headers(admin))).status_code == 404

    # DELETE removes it from public immediately
    resp = await client.delete(f"/admin/website/sponsors/{created['id']}", headers=_headers(admin))
    assert resp.status_code == 204, resp.text
    public = (await client.get("/public/sponsors")).json()
    assert all(s["name"] != "Test Academy Renamed" for s in public["academic"])
