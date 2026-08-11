"""P5-6 router tests — prerequisite gating over HTTP, plus the /missions/graph
routing-order regression (must not be swallowed by /missions/{mission_id}).
Unified onto `Prerequisite` (7B-2) — these tests exercise the mission-mission
slice of the DAG; `tests/routers/lms/test_lms_prerequisites.py` covers the
course-involving edges. Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.curriculum import Prerequisite
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User
from app.services.missions import decide_attempt, start_attempt


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Prereq Router User", email=f"pr-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _mission(db, *, author, title="Mission") -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title=title, slug=f"{title.lower().replace(' ', '-')}-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=20)
    db.add(variant)
    await db.flush()
    return mission, variant


def _requires_mission(mission_id: uuid.UUID, requires_id: uuid.UUID) -> Prerequisite:
    return Prerequisite(item_type="mission", item_id=mission_id, requires_type="mission", requires_id=requires_id)


@pytest.mark.asyncio
async def test_missions_graph_route_is_not_swallowed_by_mission_id_route(db, client):
    author = await _user(db, roles=["operations"])
    await _mission(db, author=author)
    await db.commit()
    student = await _user(db)

    resp = await client.get("/missions/graph", headers=_headers(student))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_catalog_and_detail_report_locked_state(db, client):
    author = await _user(db, roles=["operations"])
    basic, basic_variant = await _mission(db, author=author, title="Catalog Basic")
    advanced, _ = await _mission(db, author=author, title="Catalog Advanced")
    db.add(_requires_mission(advanced.id, basic.id))
    await db.commit()
    student = await _user(db)
    await db.commit()

    catalog = await client.get("/missions", headers=_headers(student))
    by_id = {m["id"]: m for m in catalog.json()}
    assert by_id[str(basic.id)]["locked"] is False
    assert by_id[str(advanced.id)]["locked"] is True

    detail = await client.get(f"/missions/{advanced.id}", headers=_headers(student))
    body = detail.json()
    assert body["locked"] is True
    assert body["prerequisites"] == [
        {"item_type": "mission", "item_id": str(basic.id), "title": "Catalog Basic", "satisfied": False}
    ]


@pytest.mark.asyncio
async def test_starting_a_locked_mission_is_forbidden(db, client):
    author = await _user(db, roles=["operations"])
    basic, _ = await _mission(db, author=author, title="Gate Basic")
    advanced, advanced_variant = await _mission(db, author=author, title="Gate Advanced")
    db.add(_requires_mission(advanced.id, basic.id))
    await db.commit()
    student = await _user(db)
    await db.commit()

    resp = await client.post(
        f"/missions/{advanced.id}/attempts", headers=_headers(student),
        json={"variant_id": str(advanced_variant.id)},
    )
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_starting_unlocks_after_passing_the_prerequisite(db, client):
    author = await _user(db, roles=["operations"])
    basic, basic_variant = await _mission(db, author=author, title="Unlock Basic")
    advanced, advanced_variant = await _mission(db, author=author, title="Unlock Advanced")
    db.add(_requires_mission(advanced.id, basic.id))
    await db.commit()
    student = await _user(db)
    await db.commit()

    attempt = await start_attempt(db, user_id=student.id, mission_id=basic.id, variant_id=basic_variant.id)
    await decide_attempt(db, attempt=attempt, passed=True, score=90)
    await db.commit()

    resp = await client.post(
        f"/missions/{advanced.id}/attempts", headers=_headers(student),
        json={"variant_id": str(advanced_variant.id)},
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_an_unrelated_mission_has_no_prerequisites_and_is_always_available(db, client):
    author = await _user(db, roles=["operations"])
    unrelated, unrelated_variant = await _mission(db, author=author, title="Unrelated")
    # Some other, unrelated DAG edge exists elsewhere in the system — must
    # not leak into this mission's own (empty) prerequisite set.
    other_a, _ = await _mission(db, author=author, title="Other A")
    other_b, _ = await _mission(db, author=author, title="Other B")
    db.add(_requires_mission(other_b.id, other_a.id))
    await db.commit()
    student = await _user(db)
    await db.commit()

    detail = await client.get(f"/missions/{unrelated.id}", headers=_headers(student))
    assert detail.json()["locked"] is False
    assert detail.json()["prerequisites"] == []

    start = await client.post(
        f"/missions/{unrelated.id}/attempts", headers=_headers(student),
        json={"variant_id": str(unrelated_variant.id)},
    )
    assert start.status_code == 201
