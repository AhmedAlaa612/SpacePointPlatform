"""P5-5 router tests — authoring a `kind='mission'` module item and reading
it back through the student surface. Redis-free (uses the `client` fixture).
"""

import uuid

import pytest

from app.core.security import create_access_token
from app.models.lms import Course, CourseModule, Enrollment
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User
from app.services.missions import decide_attempt, start_attempt


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Embed Router User", email=f"er-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _mission_with_variant(db, *, author, points=40) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Router Embed Mission", slug=f"router-embed-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=points)
    db.add(variant)
    await db.flush()
    return mission, variant


@pytest.mark.asyncio
async def test_create_mission_item_requires_mission_id(db, client):
    ops = await _user(db)
    course = Course(id=uuid.uuid4(), title="C", created_by=ops.id)
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.commit()

    bad = await client.post(
        f"/lms/admin/modules/{module.id}/items", headers=_headers(ops),
        json={"kind": "mission", "content": {}},
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_create_and_read_mission_item_end_to_end(db, client):
    ops = await _user(db)
    mission, variant = await _mission_with_variant(db, author=ops)
    course = Course(id=uuid.uuid4(), title="Embedding Course", created_by=ops.id, is_published=True)
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.commit()

    create = await client.post(
        f"/lms/admin/modules/{module.id}/items", headers=_headers(ops),
        json={"kind": "mission", "content": {"mission_id": str(mission.id), "variant_id": str(variant.id)}},
    )
    assert create.status_code == 201, create.text
    item_id = create.json()["id"]

    student = await _user(db, roles=["student"])
    db.add(Enrollment(id=uuid.uuid4(), user_id=student.id, course_id=course.id, source="self"))
    await db.commit()

    read = await client.get(f"/lms/modules/{module.id}", headers=_headers(student))
    assert read.status_code == 200, read.text
    item_out = read.json()["items"][0]
    assert item_out["kind"] == "mission"
    assert item_out["content"]["mission_id"] == str(mission.id)
    assert item_out["content"]["mission_title"] == "Router Embed Mission"
    assert item_out["content"]["points"] == 40
    assert item_out["content"]["attempt_status"] is None
    assert item_out["status"] is None

    # Pass the mission through the missions surface directly (not through
    # this item) — rule ①, completion flows one way only.
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    await decide_attempt(db, attempt=attempt, passed=True, score=90)
    await db.commit()

    read_again = await client.get(f"/lms/modules/{module.id}", headers=_headers(student))
    item_out2 = read_again.json()["items"][0]
    assert item_out2["content"]["attempt_status"] == "passed"
    assert item_out2["status"] == "completed"
