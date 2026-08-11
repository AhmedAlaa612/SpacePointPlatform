"""7B-2 (Missions Phase 2B, 2026-08-12) — the course side of the unified
prerequisite DAG over HTTP: catalog/detail report `locked`, self-enroll
403s on an unmet prerequisite, and the new `/lms/admin/prerequisites` CRUD
surface (the first admin path either mission or course prerequisite edges
have ever had). `tests/routers/missions/test_missions_prerequisites_router.py`
covers the mission side. Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms import Course, CourseModule, ModuleItem
from app.models.user import User
from app.services.lms import item_progress


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Prereq HTTP User", email=f"ph-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _one_item_course(db, *, author, title="Course") -> tuple[Course, ModuleItem]:
    course = Course(id=uuid.uuid4(), title=title, created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="text", content={"body": "x"})
    db.add(item)
    await db.flush()
    return course, item


@pytest.mark.asyncio
async def test_catalog_and_detail_report_locked_for_an_unmet_course_prerequisite(db, client):
    author = await _user(db, roles=["operations"])
    basic, _ = await _one_item_course(db, author=author, title="Prereq Basic")
    advanced, _ = await _one_item_course(db, author=author, title="Prereq Advanced")
    student = await _user(db)
    await db.commit()

    add = await client.post(
        "/lms/admin/prerequisites", headers=_headers(author),
        json={
            "item_type": "course", "item_id": str(advanced.id),
            "requires_type": "course", "requires_id": str(basic.id),
        },
    )
    assert add.status_code == 201, add.text

    catalog = await client.get("/lms/catalog", headers=_headers(student))
    by_id = {c["id"]: c for c in catalog.json()}
    assert by_id[str(basic.id)]["locked"] is False
    assert by_id[str(advanced.id)]["locked"] is True

    detail = await client.get(f"/lms/courses/{advanced.id}", headers=_headers(student))
    body = detail.json()
    assert body["locked"] is True
    assert body["prerequisites"] == [
        {"item_type": "course", "item_id": str(basic.id), "title": "Prereq Basic", "satisfied": False}
    ]


@pytest.mark.asyncio
async def test_self_enroll_is_blocked_then_allowed_once_the_prerequisite_is_met(db, client):
    author = await _user(db, roles=["operations"])
    basic, basic_item = await _one_item_course(db, author=author, title="Gate Basic")
    advanced, _ = await _one_item_course(db, author=author, title="Gate Advanced")
    student = await _user(db)
    await db.commit()

    await client.post(
        "/lms/admin/prerequisites", headers=_headers(author),
        json={
            "item_type": "course", "item_id": str(advanced.id),
            "requires_type": "course", "requires_id": str(basic.id),
        },
    )

    denied = await client.post("/lms/enroll", headers=_headers(student), json={"course_id": str(advanced.id)})
    assert denied.status_code == http_status.HTTP_403_FORBIDDEN

    await item_progress(db, user_id=student.id, item_id=basic_item.id, action="text-viewed")
    await db.commit()

    allowed = await client.post("/lms/enroll", headers=_headers(student), json={"course_id": str(advanced.id)})
    assert allowed.status_code == 200, allowed.text


@pytest.mark.asyncio
async def test_admin_prerequisites_require_content_role(db, client):
    student = await _user(db, roles=["student"])
    resp = await client.get(
        "/lms/admin/prerequisites", headers=_headers(student),
        params={"item_type": "course", "item_id": str(uuid.uuid4())},
    )
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_admin_can_add_list_and_remove_a_prerequisite_edge(db, client):
    author = await _user(db, roles=["operations"])
    basic, _ = await _one_item_course(db, author=author, title="CRUD Basic")
    advanced, _ = await _one_item_course(db, author=author, title="CRUD Advanced")
    await db.commit()

    empty = await client.get(
        "/lms/admin/prerequisites", headers=_headers(author),
        params={"item_type": "course", "item_id": str(advanced.id)},
    )
    assert empty.json() == []

    add = await client.post(
        "/lms/admin/prerequisites", headers=_headers(author),
        json={
            "item_type": "course", "item_id": str(advanced.id),
            "requires_type": "course", "requires_id": str(basic.id),
        },
    )
    assert add.status_code == 201, add.text
    assert add.json()["requires_title"] == "CRUD Basic"

    listed = await client.get(
        "/lms/admin/prerequisites", headers=_headers(author),
        params={"item_type": "course", "item_id": str(advanced.id)},
    )
    assert len(listed.json()) == 1

    removed = await client.request(
        "DELETE", "/lms/admin/prerequisites", headers=_headers(author),
        params={
            "item_type": "course", "item_id": str(advanced.id),
            "requires_type": "course", "requires_id": str(basic.id),
        },
    )
    assert removed.status_code == http_status.HTTP_204_NO_CONTENT

    after = await client.get(
        "/lms/admin/prerequisites", headers=_headers(author),
        params={"item_type": "course", "item_id": str(advanced.id)},
    )
    assert after.json() == []


@pytest.mark.asyncio
async def test_admin_add_prerequisite_rejects_self_reference_and_missing_item(db, client):
    author = await _user(db, roles=["operations"])
    course, _ = await _one_item_course(db, author=author, title="Self Ref")
    await db.commit()

    self_ref = await client.post(
        "/lms/admin/prerequisites", headers=_headers(author),
        json={
            "item_type": "course", "item_id": str(course.id),
            "requires_type": "course", "requires_id": str(course.id),
        },
    )
    assert self_ref.status_code == http_status.HTTP_400_BAD_REQUEST

    missing = await client.post(
        "/lms/admin/prerequisites", headers=_headers(author),
        json={
            "item_type": "course", "item_id": str(course.id),
            "requires_type": "mission", "requires_id": str(uuid.uuid4()),
        },
    )
    assert missing.status_code == http_status.HTTP_404_NOT_FOUND
