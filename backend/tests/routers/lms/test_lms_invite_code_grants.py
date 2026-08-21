"""Invite-code course/path grants (2026-08-21) — `/lms/admin/invite-codes/
{id}/grants`, the signup-time auto-enrol hook, and the learning-path bulk
grant endpoint (`POST /lms/admin/learning-paths/{id}/enrollments/bulk`).
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.instructors.invitation_code import InvitationCode
from app.models.lms import Course, Enrollment
from app.models.lms.invite_grant import InvitationCodeGrant
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.user import User


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ops Admin", email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db, *, name="Student", code=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name=name, email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["student"], status="active", invitation_code_used=code,
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _course(db, *, author, **kw) -> Course:
    course = Course(
        id=uuid.uuid4(), title=kw.pop("title", f"Course {uuid.uuid4().hex[:8]}"), created_by=author.id,
        is_published=True, **kw,
    )
    db.add(course)
    await db.flush()
    return course


async def _path_with_steps(db, *, author, n=2) -> tuple[LearningPath, list[Course]]:
    path = LearningPath(id=uuid.uuid4(), title=f"Path {uuid.uuid4().hex[:8]}", created_by=author.id, is_published=True)
    db.add(path)
    await db.flush()
    courses = [await _course(db, author=author) for _ in range(n)]
    for i, c in enumerate(courses, start=1):
        db.add(LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=c.id, position=i))
    await db.flush()
    return path, courses


async def _code(db, *, code="BATCH1") -> InvitationCode:
    row = InvitationCode(id=uuid.uuid4(), code=code, kind="student", is_active=True, max_uses=100, used_count=0)
    db.add(row)
    await db.flush()
    return row


# ── admin grant CRUD ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_creating_a_course_grant_enrols_existing_code_holders_immediately(db, client):
    ops = await _ops(db)
    code = await _code(db)
    author = await _ops(db)
    course = await _course(db, author=author)
    old_holder = await _student(db, name="Old", code=code.code)
    unrelated = await _student(db, name="Unrelated", code="OTHERCODE")
    await db.commit()

    resp = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"course_id": str(course.id)},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["accounts_enrolled"] == 1
    assert body["grant"]["product_type"] == "course"
    assert body["grant"]["course_title"] == course.title

    enrolled = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == old_holder.id, Enrollment.course_id == course.id)
    )).scalars().first()
    assert enrolled is not None
    assert enrolled.status == "active" and enrolled.source == "invite_code"

    untouched = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == unrelated.id, Enrollment.course_id == course.id)
    )).scalars().first()
    assert untouched is None


@pytest.mark.asyncio
async def test_creating_a_path_grant_enrols_every_step_course(db, client):
    ops = await _ops(db)
    code = await _code(db)
    author = await _ops(db)
    path, (c1, c2) = await _path_with_steps(db, author=author)
    holder = await _student(db, code=code.code)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops),
        json={"learning_path_id": str(path.id)},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["grant"]["product_type"] == "learning_path"

    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == holder.id)
    )).scalars().all()
    assert {r.course_id for r in rows} == {c1.id, c2.id}


@pytest.mark.asyncio
async def test_duplicate_grant_is_409(db, client):
    ops = await _ops(db)
    code = await _code(db)
    author = await _ops(db)
    course = await _course(db, author=author)
    await db.commit()

    first = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"course_id": str(course.id)},
    )
    assert first.status_code == 201

    dup = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"course_id": str(course.id)},
    )
    assert dup.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_grant_requires_exactly_one_of_course_or_path(db, client):
    ops = await _ops(db)
    code = await _code(db)
    await db.commit()

    neither = await client.post(f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={})
    assert neither.status_code == http_status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_list_grants(db, client):
    ops = await _ops(db)
    code = await _code(db)
    author = await _ops(db)
    course = await _course(db, author=author)
    await db.commit()

    await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"course_id": str(course.id)},
    )
    listed = await client.get(f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops))
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["course_id"] == str(course.id)


@pytest.mark.asyncio
async def test_deleting_a_grant_does_not_revoke_existing_access(db, client):
    ops = await _ops(db)
    code = await _code(db)
    author = await _ops(db)
    course = await _course(db, author=author)
    holder = await _student(db, code=code.code)
    await db.commit()

    created = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"course_id": str(course.id)},
    )
    grant_id = created.json()["grant"]["id"]

    deleted = await client.delete(
        f"/lms/admin/invite-codes/{code.id}/grants/{grant_id}", headers=_headers(ops),
    )
    assert deleted.status_code == 204

    still_there = (await db.execute(
        select(InvitationCodeGrant).where(InvitationCodeGrant.id == uuid.UUID(grant_id))
    )).scalars().first()
    assert still_there is None

    enrolled = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == holder.id, Enrollment.course_id == course.id)
    )).scalars().first()
    assert enrolled is not None and enrolled.status == "active", "removing the rule never revokes what it already granted"


# ── signup-time auto-enrol ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_new_signup_on_a_granted_code_is_auto_enrolled(db, client):
    ops = await _ops(db)
    code = await _code(db, code="GRANTBATCH")
    author = await _ops(db)
    course = await _course(db, author=author)
    await db.commit()

    await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants", headers=_headers(ops), json={"course_id": str(course.id)},
    )

    resp = await client.post("/auth/signup", json={
        "invite_code": "grantbatch",
        "full_name": "Fresh Signup", "email": "freshsignup@example.com", "password": "pass-fresh",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text

    user = (await db.execute(select(User).where(User.email == "freshsignup@example.com"))).scalars().first()
    enrolled = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == user.id, Enrollment.course_id == course.id)
    )).scalars().first()
    assert enrolled is not None
    assert enrolled.status == "active" and enrolled.source == "invite_code"


# ── learning path bulk grant ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_grant_path_by_role_enrols_every_step(db, client):
    ops = await _ops(db)
    author = await _ops(db)
    path, (c1, c2) = await _path_with_steps(db, author=author)
    facilitator = User(
        id=uuid.uuid4(), full_name="Facil", email=f"facil-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["facilitator"], status="active",
    )
    db.add(facilitator)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/learning-paths/{path.id}/enrollments/bulk", headers=_headers(ops),
        json={"role": "facilitator"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["granted"] == 1

    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == facilitator.id)
    )).scalars().all()
    assert {r.course_id for r in rows} == {c1.id, c2.id}


@pytest.mark.asyncio
async def test_bulk_grant_path_counts_partial_owner_as_already_enrolled(db, client):
    ops = await _ops(db)
    author = await _ops(db)
    path, (c1, c2) = await _path_with_steps(db, author=author)
    facilitator = User(
        id=uuid.uuid4(), full_name="Facil2", email=f"facil2-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["facilitator"], status="active",
    )
    db.add(facilitator)
    await db.flush()
    db.add(Enrollment(id=uuid.uuid4(), user_id=facilitator.id, course_id=c1.id, source="ops", status="active"))
    await db.commit()

    resp = await client.post(
        f"/lms/admin/learning-paths/{path.id}/enrollments/bulk", headers=_headers(ops),
        json={"role": "facilitator"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["granted"] == 1  # not fully owned yet, so still gets the rest granted

    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == facilitator.id)
    )).scalars().all()
    assert {r.course_id for r in rows} == {c1.id, c2.id}


@pytest.mark.asyncio
async def test_bulk_grant_path_with_no_steps_is_400(db, client):
    ops = await _ops(db)
    author = await _ops(db)
    path = LearningPath(id=uuid.uuid4(), title="Empty", created_by=author.id, is_published=True)
    db.add(path)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/learning-paths/{path.id}/enrollments/bulk", headers=_headers(ops),
        json={"role": "facilitator"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST
