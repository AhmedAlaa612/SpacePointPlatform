"""P5-4 router tests — `/missions/admin/*` authoring + review surface.
Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.user import User


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Missions Admin User", email=f"ma-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _mission(db, *, author, kind="submission", status="draft", access_mode="open") -> Mission:
    mission = Mission(
        id=uuid.uuid4(), title="Test Mission", slug=f"test-{uuid.uuid4().hex[:8]}",
        kind=kind, status=status, access_mode=access_mode, authored_by=author.id,
    )
    db.add(mission)
    await db.flush()
    return mission


@pytest.mark.asyncio
async def test_admin_routes_require_content_role(db, client):
    ops = await _user(db, roles=["operations"])
    student = await _user(db, roles=["student"])

    ok = await client.get("/missions/admin", headers=_headers(ops))
    assert ok.status_code == 200

    forbidden = await client.get("/missions/admin", headers=_headers(student))
    assert forbidden.status_code == http_status.HTTP_403_FORBIDDEN

    no_auth = await client.get("/missions/admin")
    assert no_auth.status_code == http_status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_missions_admin_does_not_collide_with_mission_id_route(db, client):
    """Routing-order regression: /missions/admin is a static path that must
    not be swallowed by student_router's /missions/{mission_id}."""
    ops = await _user(db)
    resp = await client.get("/missions/admin", headers=_headers(ops))
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_mission_and_variant(db, client):
    ops = await _user(db)
    create = await client.post(
        "/missions/admin", headers=_headers(ops),
        json={"title": "Build a Radio", "slug": "build-a-radio", "kind": "submission"},
    )
    assert create.status_code == 201, create.text
    mission_id = create.json()["id"]
    assert create.json()["status"] == "draft"

    variant = await client.post(
        f"/missions/admin/{mission_id}/variants", headers=_headers(ops),
        json={"label": "Standard", "position": 1, "points": 40, "config": {}},
    )
    assert variant.status_code == 201, variant.text
    assert variant.json()["points"] == 40


@pytest.mark.asyncio
async def test_duplicate_slug_is_rejected(db, client):
    ops = await _user(db)
    body = {"title": "Dup", "slug": "dup-mission", "kind": "submission"}
    first = await client.post("/missions/admin", headers=_headers(ops), json=body)
    assert first.status_code == 201
    second = await client.post("/missions/admin", headers=_headers(ops), json=body)
    assert second.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_quiz_variant_config_rejects_zero_correct_options(db, client):
    ops = await _user(db)
    mission = await client.post(
        "/missions/admin", headers=_headers(ops),
        json={"title": "Quiz Mission", "slug": "quiz-mission-1", "kind": "quiz"},
    )
    mission_id = mission.json()["id"]
    bad = await client.post(
        f"/missions/admin/{mission_id}/variants", headers=_headers(ops),
        json={
            "label": "Standard", "position": 1, "points": 10,
            "config": {"pass_threshold": 70, "questions": [
                {"prompt": "2+2?", "options": [{"text": "4", "is_correct": False}, {"text": "5", "is_correct": False}]},
            ]},
        },
    )
    assert bad.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_publish_via_patch(db, client):
    ops = await _user(db)
    mission = await _mission(db, author=ops, status="draft")
    resp = await client.patch(
        f"/missions/admin/{mission.id}", headers=_headers(ops), json={"status": "published"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


@pytest.mark.asyncio
async def test_review_queue_and_review_attempt(db, client):
    ops = await _user(db)
    reviewer = await _user(db)
    student = await _user(db, roles=["student"])
    mission = await _mission(db, author=ops, kind="submission", status="published")
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=25)
    db.add(variant)
    await db.flush()
    attempt = MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, user_id=student.id,
        attempt_no=1, status="submitted", payload={"artifact_url": "https://example.com/x"},
    )
    db.add(attempt)
    await db.commit()

    queue = await client.get("/missions/admin/attempts/queue", headers=_headers(reviewer))
    assert queue.status_code == 200
    assert any(a["id"] == str(attempt.id) for a in queue.json())

    review = await client.post(
        f"/missions/admin/attempts/{attempt.id}/review", headers=_headers(reviewer),
        json={"passed": True, "score": 90, "review_comment": "Nice work"},
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "passed"

    queue_after = await client.get("/missions/admin/attempts/queue", headers=_headers(reviewer))
    assert not any(a["id"] == str(attempt.id) for a in queue_after.json())
