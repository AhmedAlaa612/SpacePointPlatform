"""2026-08-12 — GET /lms/admin/users: the named-individual search backing the
course/mission assignment picker. Excludes `student`, supports role + name/
email substring filters. Redis-free.
"""

import uuid

import pytest

from app.core.security import create_access_token
from app.models.user import User


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ops Admin", email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _user(db, *, full_name, email, roles) -> User:
    user = User(id=uuid.uuid4(), full_name=full_name, email=email, password_hash="x", roles=roles, status="active")
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.mark.asyncio
async def test_search_excludes_students(db, client):
    ops = await _ops(db)
    student = await _user(db, full_name="Some Student", email=f"stu-{uuid.uuid4().hex[:8]}@example.com", roles=["student"])
    facilitator = await _user(
        db, full_name="Some Facilitator", email=f"fac-{uuid.uuid4().hex[:8]}@example.com", roles=["facilitator"],
    )
    await db.commit()

    resp = await client.get("/lms/admin/users", headers=_headers(ops))
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert str(facilitator.id) in ids
    assert str(student.id) not in ids


@pytest.mark.asyncio
async def test_search_filters_by_role(db, client):
    ops = await _ops(db)
    facilitator = await _user(
        db, full_name="Filter Facilitator", email=f"ff-{uuid.uuid4().hex[:8]}@example.com", roles=["facilitator"],
    )
    intern = await _user(db, full_name="Filter Intern", email=f"fi-{uuid.uuid4().hex[:8]}@example.com", roles=["intern"])
    await db.commit()

    resp = await client.get("/lms/admin/users", headers=_headers(ops), params={"role": "facilitator"})
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert str(facilitator.id) in ids
    assert str(intern.id) not in ids


@pytest.mark.asyncio
async def test_search_filters_by_name_or_email_substring(db, client):
    ops = await _ops(db)
    match = await _user(db, full_name="Zephyr Quasar", email=f"zq-{uuid.uuid4().hex[:8]}@example.com", roles=["instructor"])
    other = await _user(db, full_name="Someone Else", email=f"other-{uuid.uuid4().hex[:8]}@example.com", roles=["instructor"])
    await db.commit()

    resp = await client.get("/lms/admin/users", headers=_headers(ops), params={"q": "zephyr"})
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert str(match.id) in ids
    assert str(other.id) not in ids


@pytest.mark.asyncio
async def test_search_requires_lms_content_role(db, client):
    intern = await _user(db, full_name="Rando Intern", email=f"ri-{uuid.uuid4().hex[:8]}@example.com", roles=["intern"])
    await db.commit()

    resp = await client.get("/lms/admin/users", headers=_headers(intern))
    assert resp.status_code == 403
