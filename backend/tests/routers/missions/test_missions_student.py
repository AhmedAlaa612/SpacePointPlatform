"""P5-4 router tests — `/missions/*` student surface, full attempt flow over
HTTP. Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms import PointEvent
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User
from sqlalchemy import select


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Missions Student", email=f"ms-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


def _q(prompt, options):
    return {"prompt": prompt, "explanation": "because", "options": options}


async def _quiz_mission(db, *, author, status="published", access_mode="open", threshold=70) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Quiz Mission", slug=f"qm-{uuid.uuid4().hex[:8]}",
        kind="quiz", status=status, access_mode=access_mode, authored_by=author.id,
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=50,
        config={
            "pass_threshold": threshold,
            "questions": [_q("2+2?", [{"text": "5", "is_correct": False}, {"text": "4", "is_correct": True}])],
        },
    )
    db.add(variant)
    await db.flush()
    return mission, variant


async def _submission_mission(db, *, author, status="published") -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Build Something", slug=f"sm-{uuid.uuid4().hex[:8]}",
        kind="submission", status=status, access_mode="open", authored_by=author.id,
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=35)
    db.add(variant)
    await db.flush()
    return mission, variant


@pytest.mark.asyncio
async def test_catalog_only_lists_published_open_missions(db, client):
    author = await _user(db, roles=["operations"])
    published, _ = await _quiz_mission(db, author=author, status="published")
    draft, _ = await _quiz_mission(db, author=author, status="draft")
    invite, _ = await _quiz_mission(db, author=author, status="published", access_mode="invite")
    await db.commit()
    student = await _user(db)

    resp = await client.get("/missions", headers=_headers(student))
    assert resp.status_code == 200
    ids = {m["id"] for m in resp.json()}
    assert str(published.id) in ids
    assert str(draft.id) not in ids
    assert str(invite.id) not in ids


@pytest.mark.asyncio
async def test_catalog_does_not_leak_quiz_answers(db, client):
    author = await _user(db, roles=["operations"])
    mission, _ = await _quiz_mission(db, author=author)
    await db.commit()
    student = await _user(db)

    resp = await client.get(f"/missions/{mission.id}", headers=_headers(student))
    assert resp.status_code == 200
    body = resp.text
    assert "is_correct" not in body
    assert "explanation" not in body


@pytest.mark.asyncio
async def test_draft_mission_404s_for_a_student(db, client):
    author = await _user(db, roles=["operations"])
    mission, _ = await _quiz_mission(db, author=author, status="draft")
    await db.commit()
    student = await _user(db)

    resp = await client.get(f"/missions/{mission.id}", headers=_headers(student))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_full_quiz_attempt_flow_passes_and_awards_points(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _quiz_mission(db, author=author)
    await db.commit()
    student = await _user(db)
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    assert start.status_code == 201, start.text
    attempt_id = start.json()["id"]
    assert start.json()["status"] == "in_progress"

    submit = await client.post(
        f"/missions/attempts/{attempt_id}/submit", headers=_headers(student), json={"answers": [1]},
    )
    assert submit.status_code == 200, submit.text
    body = submit.json()
    assert body["attempt"]["status"] == "passed"
    assert body["review"]["passed"] is True
    assert body["review"]["score"] == 100.0

    points = (await db.execute(select(PointEvent).where(PointEvent.user_id == student.id))).scalars().all()
    assert sum(p.points for p in points) == 50


@pytest.mark.asyncio
async def test_full_submission_attempt_flow_awaits_review(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _submission_mission(db, author=author)
    await db.commit()
    student = await _user(db)
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]

    submit = await client.post(
        f"/missions/attempts/{attempt_id}/submit", headers=_headers(student),
        json={"artifact_url": "https://example.com/my-work", "notes": "done"},
    )
    assert submit.status_code == 200, submit.text
    body = submit.json()
    assert body["attempt"]["status"] == "submitted"
    assert body["review"] is None

    fetched = await client.get(f"/missions/attempts/{attempt_id}", headers=_headers(student))
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "submitted"


@pytest.mark.asyncio
async def test_cannot_fetch_another_students_attempt(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _quiz_mission(db, author=author)
    await db.commit()
    student = await _user(db)
    other = await _user(db)
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]

    resp = await client.get(f"/missions/attempts/{attempt_id}", headers=_headers(other))
    assert resp.status_code == 404
