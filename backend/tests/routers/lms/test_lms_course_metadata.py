"""LMS redesign (2026-08-06) — course authoring metadata: image, outcomes,
level, track, instructor. Covers both the admin (authoring) side and the
student-facing exposure of the same fields.
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms import Course
from app.models.user import User


async def _user(db, *, roles=None, full_name="LMS User") -> User:
    user = User(
        id=uuid.uuid4(), full_name=full_name, email=f"lms-meta-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


# ── authoring ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_course_with_full_metadata(db, client):
    ops = await _user(db)
    instructor = await _user(db, roles=["facilitator"], full_name="Dr. Nnenna Eze")
    await db.commit()

    resp = await client.post(
        "/lms/admin/courses", headers=_headers(ops),
        json={
            "title": "Satellite Systems", "kind": "course",
            "outcomes": ["Explain a power budget", "Size a reaction wheel"],
            "level": "beginner", "track": "Spacecraft systems",
            "instructor_id": str(instructor.id), "instructor_title": "Lead Systems Engineer",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["outcomes"] == ["Explain a power budget", "Size a reaction wheel"]
    assert body["level"] == "beginner"
    assert body["track"] == "Spacecraft systems"
    assert body["instructor_id"] == str(instructor.id)
    assert body["instructor_name"] == "Dr. Nnenna Eze"
    assert body["instructor_title"] == "Lead Systems Engineer"
    assert body["image_url"] is None  # no image uploaded yet


@pytest.mark.asyncio
async def test_create_course_with_unknown_instructor_404s(db, client):
    ops = await _user(db)
    await db.commit()

    resp = await client.post(
        "/lms/admin/courses", headers=_headers(ops),
        json={"title": "X", "instructor_id": str(uuid.uuid4())},
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_update_course_metadata(db, client):
    ops = await _user(db)
    course = Course(id=uuid.uuid4(), title="C", created_by=ops.id)
    db.add(course)
    await db.commit()

    resp = await client.patch(
        f"/lms/admin/courses/{course.id}", headers=_headers(ops),
        json={"level": "advanced", "outcomes": ["Do a thing"]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["level"] == "advanced"
    assert resp.json()["outcomes"] == ["Do a thing"]


@pytest.mark.asyncio
async def test_upload_course_image_sets_image_url(db, client):
    ops = await _user(db)
    course = Course(id=uuid.uuid4(), title="C", created_by=ops.id)
    db.add(course)
    await db.commit()

    get_before = await client.get(f"/lms/admin/courses/{course.id}", headers=_headers(ops))
    assert get_before.json()["image_url"] is None

    resp = await client.post(
        f"/lms/admin/courses/{course.id}/image", headers=_headers(ops),
        files={"file": ("cover.jpg", b"\xff\xd8\xff\xe0fakejpegbytes", "image/jpeg")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["image_url"] is not None

    get_after = await client.get(f"/lms/admin/courses/{course.id}", headers=_headers(ops))
    assert get_after.json()["image_url"] is not None


@pytest.mark.asyncio
async def test_upload_course_image_rejects_empty_file(db, client):
    ops = await _user(db)
    course = Course(id=uuid.uuid4(), title="C", created_by=ops.id)
    db.add(course)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/courses/{course.id}/image", headers=_headers(ops),
        files={"file": ("cover.jpg", b"", "image/jpeg")},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


# ── student-facing exposure ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_catalog_exposes_image_level_track(db, client):
    ops = await _user(db)
    course = Course(
        id=uuid.uuid4(), title="Ground Ops", created_by=ops.id, is_published=True,
        level="intermediate", track="Ground segment",
    )
    db.add(course)
    await db.commit()

    await client.post(
        f"/lms/admin/courses/{course.id}/image", headers=_headers(ops),
        files={"file": ("cover.jpg", b"\xff\xd8\xff\xe0fakejpegbytes", "image/jpeg")},
    )

    student = await _user(db, roles=["student"])
    await db.commit()
    resp = await client.get("/lms/catalog", headers=_headers(student))
    assert resp.status_code == 200
    match = next(c for c in resp.json() if c["id"] == str(course.id))
    assert match["level"] == "intermediate"
    assert match["track"] == "Ground segment"
    assert match["image_url"] is not None


@pytest.mark.asyncio
async def test_course_detail_exposes_outcomes_and_instructor(db, client):
    ops = await _user(db)
    instructor = await _user(db, roles=["facilitator"], full_name="Tobi Adeyemi")
    course = Course(
        id=uuid.uuid4(), title="Orbits", created_by=ops.id, is_published=True,
        outcomes=["Explain Kepler's laws"], level="beginner",
        instructor_id=instructor.id, instructor_title="Orbital Dynamics Lead",
    )
    db.add(course)
    await db.commit()

    student = await _user(db, roles=["student"])
    await db.commit()
    resp = await client.get(f"/lms/courses/{course.id}", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["outcomes"] == ["Explain Kepler's laws"]
    assert body["instructor_name"] == "Tobi Adeyemi"
    assert body["instructor_title"] == "Orbital Dynamics Lead"


@pytest.mark.asyncio
async def test_course_detail_instructor_fields_null_when_unset(db, client):
    ops = await _user(db)
    course = Course(id=uuid.uuid4(), title="No Instructor", created_by=ops.id, is_published=True)
    db.add(course)
    await db.commit()

    student = await _user(db, roles=["student"])
    await db.commit()
    resp = await client.get(f"/lms/courses/{course.id}", headers=_headers(student))
    assert resp.status_code == 200
    body = resp.json()
    assert body["instructor_name"] is None
    assert body["outcomes"] == []
