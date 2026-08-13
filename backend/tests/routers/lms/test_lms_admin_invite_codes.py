"""Ops-managed student invite codes (2026-08-13) — `/lms/admin/invite-codes`,
plus the batch filter on the students list. Redis-free.
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.instructors.invitation_code import InvitationCode
from app.models.user import User


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ops Admin", email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db, *, name, code=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name=name, email=f"{name.lower().replace(' ', '')}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["student"], status="active", invitation_code_used=code,
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.mark.asyncio
async def test_create_list_and_update_a_student_code(db, client):
    ops = await _ops(db)
    await db.commit()

    created = await client.post(
        "/lms/admin/invite-codes", headers=_headers(ops),
        json={"code": "fall26", "label": "Fall 2026 Batch", "max_uses": 40},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["code"] == "FALL26", "codes normalise to uppercase"
    assert body["label"] == "Fall 2026 Batch"
    assert body["signups"] == 0

    listed = await client.get("/lms/admin/invite-codes", headers=_headers(ops))
    assert [c["code"] for c in listed.json()] == ["FALL26"]

    updated = await client.patch(
        f"/lms/admin/invite-codes/{body['id']}", headers=_headers(ops),
        json={"label": "Fall 2026 — Dubai", "is_active": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["label"] == "Fall 2026 — Dubai"
    assert updated.json()["is_active"] is False


@pytest.mark.asyncio
async def test_duplicate_codes_are_rejected_across_both_pools(db, client):
    """`code` is unique table-wide, so clashing with an instructor code has
    to be a clean 409 rather than an IntegrityError 500."""
    ops = await _ops(db)
    db.add(InvitationCode(id=uuid.uuid4(), code="SHARED", kind="instructor", is_active=True, max_uses=5))
    await db.commit()

    resp = await client.post(
        "/lms/admin/invite-codes", headers=_headers(ops), json={"code": "shared"},
    )
    assert resp.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_the_ops_list_never_shows_instructor_codes(db, client):
    ops = await _ops(db)
    db.add(InvitationCode(id=uuid.uuid4(), code="INSTR1", kind="instructor", is_active=True, max_uses=5))
    db.add(InvitationCode(id=uuid.uuid4(), code="STUD1", kind="student", is_active=True, max_uses=5))
    await db.commit()

    resp = await client.get("/lms/admin/invite-codes", headers=_headers(ops))
    codes = {c["code"] for c in resp.json()}
    assert "STUD1" in codes
    assert "INSTR1" not in codes


@pytest.mark.asyncio
async def test_a_used_code_cannot_be_deleted_or_renamed(db, client):
    """users.invitation_code_used is a plain string, not an FK — deleting or
    renaming the code would orphan its students from the batch filter."""
    ops = await _ops(db)
    row = InvitationCode(id=uuid.uuid4(), code="INUSE", kind="student", is_active=True, max_uses=50)
    db.add(row)
    await db.flush()
    await _student(db, name="Signed Up", code="INUSE")
    await db.commit()

    deleted = await client.delete(f"/lms/admin/invite-codes/{row.id}", headers=_headers(ops))
    assert deleted.status_code == http_status.HTTP_409_CONFLICT
    assert "deactivate" in deleted.json()["detail"].lower()

    renamed = await client.patch(
        f"/lms/admin/invite-codes/{row.id}", headers=_headers(ops), json={"code": "RENAMED"},
    )
    assert renamed.status_code == http_status.HTTP_409_CONFLICT

    # Relabelling is always fine — that's the documented escape hatch.
    relabel = await client.patch(
        f"/lms/admin/invite-codes/{row.id}", headers=_headers(ops), json={"label": "Renamed Batch"},
    )
    assert relabel.status_code == 200
    assert relabel.json()["signups"] == 1


@pytest.mark.asyncio
async def test_an_unused_code_can_be_deleted(db, client):
    ops = await _ops(db)
    row = InvitationCode(id=uuid.uuid4(), code="UNUSED", kind="student", is_active=True, max_uses=50)
    db.add(row)
    await db.commit()

    resp = await client.delete(f"/lms/admin/invite-codes/{row.id}", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_204_NO_CONTENT
    assert (await db.execute(
        select(InvitationCode).where(InvitationCode.code == "UNUSED")
    )).scalars().first() is None


@pytest.mark.asyncio
async def test_students_can_be_filtered_by_batch(db, client):
    ops = await _ops(db)
    db.add(InvitationCode(
        id=uuid.uuid4(), code="BATCHA", kind="student", label="Batch A", is_active=True, max_uses=50,
    ))
    a = await _student(db, name="Anna Batch", code="BATCHA")
    b = await _student(db, name="Bilal Other", code="BATCHB")
    legacy = await _student(db, name="Legacy Learner", code=None)
    await db.commit()

    filtered = await client.get(
        "/lms/admin/students", headers=_headers(ops), params={"invite_code": "batcha"},
    )
    assert filtered.status_code == 200
    rows = filtered.json()
    assert {r["id"] for r in rows} == {str(a.id)}
    assert rows[0]["invite_label"] == "Batch A", "the batch label, not just the raw code"

    # Students who predate the gate are reachable through the sentinel.
    none_rows = await client.get(
        "/lms/admin/students", headers=_headers(ops), params={"invite_code": "none"},
    )
    none_ids = {r["id"] for r in none_rows.json()}
    assert str(legacy.id) in none_ids
    assert str(a.id) not in none_ids
    assert str(b.id) not in none_ids


@pytest.mark.asyncio
async def test_invite_code_routes_require_content_role(db, client):
    student = await _student(db, name="Rando Student")
    await db.commit()
    resp = await client.get("/lms/admin/invite-codes", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN
