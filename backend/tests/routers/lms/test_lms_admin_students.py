"""2026-08-12 — GET /lms/admin/students and GET /lms/admin/students/{id}:
the student-management list/profile pages. Redis-free.
"""

import uuid
from datetime import date

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ops Admin", email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db, *, full_name, nickname=None, cohort_id=None) -> User:
    contact = Contact(id=uuid.uuid4(), full_name=full_name, contact_roles=["student"])
    db.add(contact)
    await db.flush()
    student = User(
        id=uuid.uuid4(), full_name=full_name, email=f"{full_name.lower().replace(' ', '')}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id, nickname=nickname,
    )
    db.add(student)
    await db.flush()
    if cohort_id is not None:
        db.add(Registration(
            id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort_id, status="registered",
            ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="waived",
        ))
        await db.flush()
    return student


async def _cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"PG-{uuid.uuid4().hex[:8]}", name="Student Mgmt Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Student Mgmt Cohort", status="running",
        starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 5),
    )
    db.add(cohort)
    await db.flush()
    return cohort


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.mark.asyncio
async def test_search_students_filters_by_name(db, client):
    ops = await _ops(db)
    match = await _student(db, full_name="Searchable Sam")
    other = await _student(db, full_name="Someone Else")
    await db.commit()

    resp = await client.get("/lms/admin/students", headers=_headers(ops), params={"q": "searchable"})
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert str(match.id) in ids
    assert str(other.id) not in ids


@pytest.mark.asyncio
async def test_search_students_excludes_staff(db, client):
    ops = await _ops(db)
    student = await _student(db, full_name="Just Student")
    await db.commit()

    resp = await client.get("/lms/admin/students", headers=_headers(ops))
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.json()}
    assert str(student.id) in ids
    assert str(ops.id) not in ids


@pytest.mark.asyncio
async def test_student_profile_includes_nickname_and_programs(db, client):
    ops = await _ops(db)
    cohort = await _cohort(db)
    student = await _student(db, full_name="Profile Pat", nickname="NebulaFalcon482", cohort_id=cohort.id)
    await db.commit()

    resp = await client.get(f"/lms/admin/students/{student.id}", headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["full_name"] == "Profile Pat"
    assert body["nickname"] == "NebulaFalcon482"
    assert len(body["programs"]) == 1
    assert body["programs"][0]["cohort_id"] == str(cohort.id)


@pytest.mark.asyncio
async def test_student_profile_404s_for_non_student_or_unknown_user(db, client):
    ops = await _ops(db)
    await db.commit()

    resp = await client.get(f"/lms/admin/students/{ops.id}", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND

    resp = await client.get(f"/lms/admin/students/{uuid.uuid4()}", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_students_endpoints_require_content_role(db, client):
    student = await _student(db, full_name="Rando")
    await db.commit()

    resp = await client.get("/lms/admin/students", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN
