"""7B-7 (Missions Phase 2B, 2026-08-12) — mission-manager scoped surface:
admin assignment CRUD (`/missions/admin/{id}/managers`) and the manager's
own view (`/missions/manager/*`). Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.user import User


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Manager Test User", email=f"mgr-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _mission(db, *, author, title="Manager Mission") -> tuple[Mission, MissionVariant]:
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


# ── admin assignment CRUD ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_only_staff_can_assign_a_manager(db, client):
    ops = await _user(db, roles=["operations"])
    intern = await _user(db, roles=["intern"])
    mission, _ = await _mission(db, author=ops)
    await db.commit()

    resp = await client.post(
        f"/missions/admin/{mission.id}/managers", headers=_headers(intern), json={"user_id": str(intern.id)},
    )
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_assign_list_and_revoke_a_manager(db, client):
    ops = await _user(db, roles=["operations"])
    intern = await _user(db, roles=["intern"])
    mission, _ = await _mission(db, author=ops)
    await db.commit()

    empty = await client.get(f"/missions/admin/{mission.id}/managers", headers=_headers(ops))
    assert empty.json() == []

    assign = await client.post(
        f"/missions/admin/{mission.id}/managers", headers=_headers(ops), json={"user_id": str(intern.id)},
    )
    assert assign.status_code == 201, assign.text
    assert assign.json()["full_name"] == "Manager Test User"

    dup = await client.post(
        f"/missions/admin/{mission.id}/managers", headers=_headers(ops), json={"user_id": str(intern.id)},
    )
    assert dup.status_code == http_status.HTTP_409_CONFLICT

    listed = await client.get(f"/missions/admin/{mission.id}/managers", headers=_headers(ops))
    assert len(listed.json()) == 1

    revoke = await client.delete(f"/missions/admin/{mission.id}/managers/{intern.id}", headers=_headers(ops))
    assert revoke.status_code == http_status.HTTP_204_NO_CONTENT

    after = await client.get(f"/missions/admin/{mission.id}/managers", headers=_headers(ops))
    assert after.json() == []


# ── manager surface ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_stranger_cannot_see_stats_or_queue(db, client):
    ops = await _user(db, roles=["operations"])
    stranger = await _user(db, roles=["intern"])
    mission, _ = await _mission(db, author=ops)
    await db.commit()

    stats = await client.get(f"/missions/manager/{mission.id}/stats", headers=_headers(stranger))
    assert stats.status_code == http_status.HTTP_403_FORBIDDEN
    queue = await client.get(f"/missions/manager/{mission.id}/queue", headers=_headers(stranger))
    assert queue.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_staff_can_use_the_manager_surface_without_being_assigned(db, client):
    ops = await _user(db, roles=["operations"])
    mission, _ = await _mission(db, author=ops)
    await db.commit()

    stats = await client.get(f"/missions/manager/{mission.id}/stats", headers=_headers(ops))
    assert stats.status_code == 200, stats.text
    assert stats.json()["total_students"] == 0


@pytest.mark.asyncio
async def test_an_assigned_manager_sees_stats_and_queue_and_can_review(db, client):
    ops = await _user(db, roles=["operations"])
    manager = await _user(db, roles=["intern"])
    student = await _user(db)
    mission, variant = await _mission(db, author=ops)
    await client.post(
        f"/missions/admin/{mission.id}/managers", headers=_headers(ops), json={"user_id": str(manager.id)},
    )
    attempt = MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, user_id=student.id,
        attempt_no=1, status="submitted", payload={"artifact_url": "https://example.com/x"},
    )
    db.add(attempt)
    await db.commit()

    stats = await client.get(f"/missions/manager/{mission.id}/stats", headers=_headers(manager))
    assert stats.status_code == 200, stats.text
    assert stats.json()["total_attempts"] == 1

    queue = await client.get(f"/missions/manager/{mission.id}/queue", headers=_headers(manager))
    assert queue.status_code == 200
    assert any(a["id"] == str(attempt.id) for a in queue.json())

    mine = await client.get("/missions/manager/mine", headers=_headers(manager))
    assert mine.status_code == 200
    assert [m["mission_id"] for m in mine.json()] == [str(mission.id)]

    review = await client.post(
        f"/missions/manager/attempts/{attempt.id}/review", headers=_headers(manager),
        json={"passed": True, "score": 88, "review_comment": "Solid work"},
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "passed"


@pytest.mark.asyncio
async def test_a_manager_of_one_mission_cannot_review_another(db, client):
    ops = await _user(db, roles=["operations"])
    manager = await _user(db, roles=["intern"])
    student = await _user(db)
    managed_mission, _ = await _mission(db, author=ops, title="Managed Mission")
    other_mission, other_variant = await _mission(db, author=ops, title="Other Mission")
    await client.post(
        f"/missions/admin/{managed_mission.id}/managers", headers=_headers(ops), json={"user_id": str(manager.id)},
    )
    other_attempt = MissionAttempt(
        id=uuid.uuid4(), mission_id=other_mission.id, variant_id=other_variant.id, user_id=student.id,
        attempt_no=1, status="submitted", payload={},
    )
    db.add(other_attempt)
    await db.commit()

    denied = await client.get(f"/missions/manager/{other_mission.id}/stats", headers=_headers(manager))
    assert denied.status_code == http_status.HTTP_403_FORBIDDEN

    denied_review = await client.post(
        f"/missions/manager/attempts/{other_attempt.id}/review", headers=_headers(manager),
        json={"passed": True, "score": 50},
    )
    assert denied_review.status_code == http_status.HTTP_403_FORBIDDEN
