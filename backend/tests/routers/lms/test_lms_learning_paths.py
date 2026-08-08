"""Learning paths (LMS redesign, 2026-08-08) — self-paced ordered course
sequences. Covers: admin CRUD + step ordering (mirrors program_curriculum's
own test shape), the student catalog/detail 404-on-unpublished rule, "start"
bulk-enrolling every step's course, and the path_progress state rollup
(done/current/mission/locked) at the service layer.
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.lms import Course, CourseModule, Enrollment, ModuleItem
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.user import User
from app.services.lms import enroll, item_progress, path_progress


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="LMS Path User",
        email=f"lms-path-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash", roles=list(roles) if roles else ["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _course(db, *, author, published=True, kind="course", **kw) -> Course:
    course = Course(
        id=uuid.uuid4(), title=kw.pop("title", f"Course {uuid.uuid4().hex[:8]}"),
        created_by=author.id, is_published=published, kind=kind, **kw,
    )
    db.add(course)
    await db.flush()
    return course


async def _path(db, *, author, published=True) -> LearningPath:
    path = LearningPath(
        id=uuid.uuid4(), title=f"Path {uuid.uuid4().hex[:8]}", created_by=author.id, is_published=published,
    )
    db.add(path)
    await db.flush()
    return path


async def _course_with_one_module_one_item(db, *, author) -> tuple[Course, ModuleItem]:
    course = await _course(db, author=author)
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="text", content={"body": "x"})
    db.add(item)
    await db.flush()
    return course, item


# ── admin CRUD + step ordering ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_learning_path_crud_and_publish(db, client):
    ops = await _user(db)
    await db.commit()

    create = await client.post(
        "/lms/admin/learning-paths", headers=_headers(ops),
        json={"title": "Space Science Foundations", "description": "Eight steps"},
    )
    assert create.status_code == 201
    path_id = create.json()["id"]
    assert create.json()["is_published"] is False

    published = await client.patch(
        f"/lms/admin/learning-paths/{path_id}", headers=_headers(ops), json={"is_published": True},
    )
    assert published.status_code == 200 and published.json()["is_published"] is True

    listed = await client.get("/lms/admin/learning-paths", headers=_headers(ops))
    assert any(p["id"] == path_id for p in listed.json())

    deleted = await client.delete(f"/lms/admin/learning-paths/{path_id}", headers=_headers(ops))
    assert deleted.status_code == 204
    missing = await client.get(f"/lms/admin/learning-paths/{path_id}", headers=_headers(ops))
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_admin_learning_path_step_binding_add_list_remove(db, client):
    ops = await _user(db)
    path = await _path(db, author=ops)
    course_a = await _course(db, author=ops, title="A")
    course_b = await _course(db, author=ops, title="B")
    await db.commit()

    add_a = await client.post(
        f"/lms/admin/learning-paths/{path.id}/steps", headers=_headers(ops),
        json={"course_id": str(course_a.id)},
    )
    assert add_a.status_code == 201 and add_a.json()["position"] == 1

    add_b = await client.post(
        f"/lms/admin/learning-paths/{path.id}/steps", headers=_headers(ops),
        json={"course_id": str(course_b.id)},
    )
    assert add_b.status_code == 201 and add_b.json()["position"] == 2

    dup = await client.post(
        f"/lms/admin/learning-paths/{path.id}/steps", headers=_headers(ops),
        json={"course_id": str(course_a.id)},
    )
    assert dup.status_code == http_status.HTTP_409_CONFLICT

    taken_position = await client.post(
        f"/lms/admin/learning-paths/{path.id}/steps", headers=_headers(ops),
        json={"course_id": str(course_a.id), "position": 1},
    )
    assert taken_position.status_code == http_status.HTTP_409_CONFLICT

    listed = await client.get(f"/lms/admin/learning-paths/{path.id}/steps", headers=_headers(ops))
    assert [s["course_id"] for s in listed.json()] == [str(course_a.id), str(course_b.id)]

    removed = await client.delete(
        f"/lms/admin/learning-paths/{path.id}/steps/{course_a.id}", headers=_headers(ops)
    )
    assert removed.status_code == 204
    remaining = (await db.execute(
        select(LearningPathStep).where(LearningPathStep.learning_path_id == path.id)
    )).scalars().all()
    assert len(remaining) == 1 and remaining[0].course_id == course_b.id


# ── student catalog / detail ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unpublished_path_404s_for_students(db, client):
    ops = await _user(db)
    student = await _user(db, roles=["student"])
    path = await _path(db, author=ops, published=False)
    await db.commit()

    resp = await client.get(f"/lms/learning-paths/{path.id}", headers=_headers(student))
    assert resp.status_code == 404

    catalog = await client.get("/lms/learning-paths", headers=_headers(student))
    assert all(p["id"] != str(path.id) for p in catalog.json())


@pytest.mark.asyncio
async def test_start_path_bulk_enrolls_every_step_course(db, client):
    ops = await _user(db)
    student = await _user(db, roles=["student"])
    path = await _path(db, author=ops)
    course_a, _item_a = await _course_with_one_module_one_item(db, author=ops)
    course_b, _item_b = await _course_with_one_module_one_item(db, author=ops)
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_a.id, position=1))
    db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course_b.id, position=2))
    await db.commit()

    resp = await client.post(f"/lms/learning-paths/{path.id}/start", headers=_headers(student))
    assert resp.status_code == 200
    body = resp.json()
    assert body["course_count"] == 2
    assert {s["course_id"] for s in body["steps"]} == {str(course_a.id), str(course_b.id)}

    enrollments = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id)
    )).scalars().all()
    assert {e.course_id for e in enrollments} == {course_a.id, course_b.id}
    assert all(e.status == "active" and e.source == "self" for e in enrollments)

    # idempotent — calling start again doesn't duplicate or error
    again = await client.post(f"/lms/learning-paths/{path.id}/start", headers=_headers(student))
    assert again.status_code == 200
    enrollments_again = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id)
    )).scalars().all()
    assert len(enrollments_again) == 2


# ── path_progress state rollup (service layer) ──────────────────────────────

@pytest.mark.asyncio
async def test_path_progress_state_rollup_done_current_mission_locked(db):
    ops = await _user(db)
    student = await _user(db, roles=["student"])

    done_course, done_item = await _course_with_one_module_one_item(db, author=ops)
    current_course, _current_item = await _course_with_one_module_one_item(db, author=ops)
    mission_course = await _course(db, author=ops, kind="mission")
    locked_course, _locked_item = await _course_with_one_module_one_item(db, author=ops)
    path = await _path(db, author=ops)
    steps = [
        LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=done_course.id, position=1),
        LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=current_course.id, position=2),
        LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=mission_course.id, position=3),
        LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=locked_course.id, position=4),
    ]
    db.add_all(steps)
    await db.commit()

    await enroll(db, user_id=student.id, course_id=done_course.id)
    await enroll(db, user_id=student.id, course_id=current_course.id)
    await enroll(db, user_id=student.id, course_id=locked_course.id)
    await item_progress(db, user_id=student.id, item_id=done_item.id, action="text-viewed")
    await db.commit()

    result = await path_progress(db, user_id=student.id, steps=steps)
    states = {row["course_id"]: row["state"] for row in result["steps"]}
    assert states[done_course.id] == "done"
    assert states[current_course.id] == "current"
    assert states[mission_course.id] == "mission"
    assert states[locked_course.id] == "locked"
    # mission step never counts toward course_count / pct denominator
    assert result["course_count"] == 3
    assert result["mission_count"] == 1
    assert result["pct"] == 33  # 1 of 3 course-kind steps fully done
