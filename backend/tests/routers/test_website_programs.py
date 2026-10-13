"""Step 2 — Core Programs & AED Pricing Management.

Public GET /public/website/programs is unauthenticated and returns only
published programs ordered by display_order; admin GET/PUT
/admin/website/programs/* require the admin role. An admin price/title
edit must be immediately visible on the public endpoint (the marketing
site reads it with no redeploy).
"""

import uuid

import pytest
from sqlalchemy import delete

from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.website_program import WebsiteProgram

SEEDS = [
    {
        "slug": "space-explorer",
        "title": "Space Explorer",
        "tagline": "First steps into space science and satellite basics",
        "category": "Aerospace Engineering",
        "level": "Beginner",
        "duration": "2 Weeks",
        "price_aed": 1500,
        "badge_text": None,
        "features_list": ["Hands-on satellite model builds"],
        "display_order": 1,
        "is_published": True,
    },
    {
        "slug": "cansat-balloon-missions",
        "title": "CanSat & Balloon Missions",
        "tagline": "Build, launch, and recover real flight payloads",
        "category": "Aerospace Engineering",
        "level": "Intermediate",
        "duration": "4 Weeks",
        "price_aed": 2500,
        "badge_text": None,
        "features_list": ["CanSat kit assembly and programming"],
        "display_order": 2,
        "is_published": True,
    },
    {
        "slug": "cubesat-flight-integration",
        "title": "CubeSat Flight Integration",
        "tagline": "Our flagship end-to-end CubeSat engineering program",
        "category": "Aerospace Engineering",
        "level": "Intermediate",
        "duration": "6 Weeks",
        "price_aed": 3500,
        "badge_text": "Flagship",
        "features_list": ["Full CubeSat subsystem integration"],
        "display_order": 3,
        "is_published": True,
    },
    {
        "slug": "ground-station-orbital-ops",
        "title": "Ground Station & Orbital Ops",
        "tagline": "Track satellites live and run real orbital operations",
        "category": "Aerospace Engineering",
        "level": "Advanced",
        "duration": "4 Weeks",
        "price_aed": 4000,
        "badge_text": "Most Popular",
        "features_list": ["Live satellite tracking sessions"],
        "display_order": 4,
        "is_published": True,
    },
]


async def _ensure_table(db):
    conn = await db.connection()
    await conn.run_sync(lambda c: WebsiteProgram.__table__.create(c, checkfirst=True))


async def _seed(db):
    await db.execute(delete(WebsiteProgram))
    await db.flush()
    for seed in SEEDS:
        db.add(WebsiteProgram(id=uuid.uuid4(), **seed))
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
async def test_public_programs_returns_seeded_four_unauthenticated(db, client):
    await _ensure_table(db)
    await _seed(db)

    resp = await client.get("/public/website/programs")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 4
    by_slug = {p["slug"]: p for p in body}
    assert by_slug["space-explorer"]["price_aed"] == 1500
    assert by_slug["space-explorer"]["level"] == "Beginner"
    assert by_slug["cansat-balloon-missions"]["price_aed"] == 2500
    assert by_slug["cubesat-flight-integration"]["price_aed"] == 3500
    assert by_slug["cubesat-flight-integration"]["badge_text"] == "Flagship"
    assert by_slug["ground-station-orbital-ops"]["price_aed"] == 4000
    assert by_slug["ground-station-orbital-ops"]["level"] == "Advanced"
    # Ordered by display_order
    assert [p["display_order"] for p in body] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_public_programs_hides_unpublished(db, client):
    await _ensure_table(db)
    await _seed(db)

    admin = await _make_user(db, ["admin"])
    programs = (await client.get("/admin/website/programs", headers=_headers(admin))).json()
    target = next(p for p in programs if p["slug"] == "space-explorer")
    resp = await client.put(
        f"/admin/website/programs/{target['id']}",
        json={"is_published": False},
        headers=_headers(admin),
    )
    assert resp.status_code == 200, resp.text

    public = (await client.get("/public/website/programs")).json()
    assert len(public) == 3
    assert all(p["slug"] != "space-explorer" for p in public)
    # Admin list still includes it
    admin_list = (await client.get("/admin/website/programs", headers=_headers(admin))).json()
    assert len(admin_list) == 4


@pytest.mark.asyncio
async def test_admin_programs_require_admin(db, client):
    await _ensure_table(db)
    await _seed(db)

    assert (await client.get("/admin/website/programs")).status_code in (401, 403)
    programs = (await client.get("/public/website/programs")).json()
    assert (
        await client.put(f"/admin/website/programs/{programs[0]['id']}", json={"price_aed": 9})
    ).status_code in (401, 403)

    student = await _make_user(db, ["student"])
    assert (await client.get("/admin/website/programs", headers=_headers(student))).status_code == 403
    assert (
        await client.put(
            f"/admin/website/programs/{programs[0]['id']}",
            json={"price_aed": 9},
            headers=_headers(student),
        )
    ).status_code == 403

    ops = await _make_user(db, ["operations"])
    assert (await client.get("/admin/website/programs", headers=_headers(ops))).status_code == 200
    assert (
        await client.put(
            f"/admin/website/programs/{programs[0]['id']}",
            json={"price_aed": 999},
            headers=_headers(ops),
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_admin_update_price_and_title_reflects_immediately_on_public(db, client):
    await _ensure_table(db)
    await _seed(db)
    admin = await _make_user(db, ["admin"])

    programs = (await client.get("/admin/website/programs", headers=_headers(admin))).json()
    target = next(p for p in programs if p["slug"] == "cubesat-flight-integration")

    resp = await client.put(
        f"/admin/website/programs/{target['id']}",
        json={"price_aed": 3750, "title": "CubeSat Flight Integration+"},
        headers=_headers(admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["price_aed"] == 3750
    assert resp.json()["title"] == "CubeSat Flight Integration+"

    public = (await client.get("/public/website/programs")).json()
    updated = next(p for p in public if p["slug"] == "cubesat-flight-integration")
    assert updated["price_aed"] == 3750
    assert updated["title"] == "CubeSat Flight Integration+"

    # Unknown id is a 404, not a 500
    resp = await client.put(
        f"/admin/website/programs/{uuid.uuid4()}",
        json={"price_aed": 1},
        headers=_headers(admin),
    )
    assert resp.status_code == 404
