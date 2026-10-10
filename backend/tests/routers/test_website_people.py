"""Step 6 — People Showcase (Team, Ambassadors, Alumni & Student Missions).

Public GETs return active rows ordered by display_order; admin CRUD for
all four domains requires the admin role. One parametrized suite covers
every domain identically.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.website_people import StudentMission, TeamMember, WebsiteAlumni, WebsiteAmbassador

DOMAINS = {
    "team": {
        "model": TeamMember,
        "public": "/public/team",
        "admin": "/admin/website/team",
        "create": {"name": "Nova Perera", "role": "Education Lead", "photo_url": "/img/nova.png"},
        "update": {"role": "Senior Education Lead", "department": "Education"},
    },
    "ambassadors": {
        "model": WebsiteAmbassador,
        "public": "/public/ambassadors",
        "admin": "/admin/website/ambassadors",
        "create": {"name": "Nova Perera", "university": "Khalifa University", "photo_url": "/img/nova.png"},
        "update": {"badge": "Campus Lead", "major": "Aerospace Engineering"},
    },
    "alumni": {
        "model": WebsiteAlumni,
        "public": "/public/alumni",
        "admin": "/admin/website/alumni",
        "create": {
            "name": "Nova Perera",
            "program_completed": "CubeSat Mastery 2025",
            "current_role": "Satellite Systems Engineer at MBRSC",
            "photo_url": "/img/nova.png",
        },
        "update": {"current_role": "Senior Satellite Systems Engineer at MBRSC"},
    },
    "student-missions": {
        "model": StudentMission,
        "public": "/public/student-missions",
        "admin": "/admin/website/student-missions",
        "create": {
            "student_name": "Nova Perera",
            "project_title": "Balloon Payload Recovery",
            "category": "Flight Operations",
            "description": "Built and recovered a high-altitude payload.",
            "metrics_json": {"Altitude": "30,000m"},
        },
        "update": {"category": "Stratospheric Biology"},
    },
}


async def _ensure_tables(db):
    conn = await db.connection()
    for domain in DOMAINS.values():
        await conn.run_sync(lambda c, t=domain["model"].__table__: t.create(c, checkfirst=True))


async def _clear(db):
    for domain in DOMAINS.values():
        await db.execute(delete(domain["model"]))
    await db.flush()


async def _seed(db, key, **overrides):
    domain = DOMAINS[key]
    payload = dict(domain["create"])
    payload.update(overrides)
    row = domain["model"](id=uuid.uuid4(), **payload)
    db.add(row)
    await db.flush()
    return row


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
@pytest.mark.parametrize("key", list(DOMAINS))
async def test_public_lists_active_ordered(db, client, key):
    await _ensure_tables(db)
    await _clear(db)
    domain = DOMAINS[key]

    await _seed(db, key, display_order=2)
    await _seed(db, key, display_order=1)
    await _seed(db, key, display_order=0, is_active=False)

    resp = await client.get(domain["public"])
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    assert [r["display_order"] for r in body] == [1, 2]

    # Inactive rows stay hidden even when everything is hidden
    admin = await _make_user(db, ["admin"])
    for row in (await client.get(domain["admin"], headers=_headers(admin))).json():
        if row["display_order"] != 0:
            await client.put(
                f"{domain['admin']}/{row['id']}", json={"is_active": False}, headers=_headers(admin)
            )
    assert (await client.get(domain["public"])).json() == []
    assert len((await client.get(domain["admin"], headers=_headers(admin))).json()) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("key", list(DOMAINS))
async def test_admin_crud_with_guards(db, client, key):
    await _ensure_tables(db)
    await _clear(db)
    domain = DOMAINS[key]
    admin = await _make_user(db, ["admin"])
    student = await _make_user(db, ["student"])

    # Guards: anonymous and non-admin are rejected everywhere
    assert (await client.get(domain["admin"])).status_code in (401, 403)
    assert (await client.post(domain["admin"], json=domain["create"])).status_code in (401, 403)
    seed = await _seed(db, key)
    assert (
        await client.put(f"{domain['admin']}/{seed.id}", json=domain["update"])
    ).status_code in (401, 403)
    assert (await client.delete(f"{domain['admin']}/{seed.id}")).status_code in (401, 403)
    assert (await client.get(domain["admin"], headers=_headers(student))).status_code == 403

    # Unknown id → 404, not 500
    assert (
        await client.put(
            f"{domain['admin']}/{uuid.uuid4()}", json=domain["update"], headers=_headers(admin)
        )
    ).status_code == 404
    assert (
        await client.delete(f"{domain['admin']}/{uuid.uuid4()}", headers=_headers(admin))
    ).status_code == 404

    # Create → visible on public immediately
    resp = await client.post(domain["admin"], json=domain["create"], headers=_headers(admin))
    assert resp.status_code == 201, resp.text
    created = resp.json()
    public = (await client.get(domain["public"])).json()
    assert any(r["id"] == created["id"] for r in public)

    # Update → reflected on public immediately
    resp = await client.put(
        f"{domain['admin']}/{created['id']}", json=domain["update"], headers=_headers(admin)
    )
    assert resp.status_code == 200, resp.text
    for field, value in domain["update"].items():
        assert resp.json()[field] == value

    # Delete → gone from public immediately
    assert (
        await client.delete(f"{domain['admin']}/{created['id']}", headers=_headers(admin))
    ).status_code == 204
    public = (await client.get(domain["public"])).json()
    assert all(r["id"] != created["id"] for r in public)
