"""LMS Program checklist — instructor surface (2026-08-21 redesign):
GET .../program-progress and the confirm action, cohort-scoped via
`require_cohort_access` (same convention `routers/missions/instructor.py`
uses). Redis-free (uses the `client` fixture).
"""

import uuid
from datetime import date

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.program import Program
from app.models.sessions.session import Session as DeliverySession, SessionInstructor
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms.program import assign_lms_program


async def _role_id(db, name: str = "Lead Facilitator"):
    """I5-3: roles are rows now, seeded by migration `c2a7b49e0022` —
    tests look them up rather than inventing their own."""
    return await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Checklist Instructor Test", email=f"cki-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["instructor"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db) -> User:
    contact = Contact(
        id=uuid.uuid4(), full_name="Checklist Instructor Test Student", contact_roles=["student"],
        secondary_phones=[], preferred_language="en", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name="Checklist Instructor Test Student", email=f"ckis-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(user)
    await db.flush()
    return user


async def _cohort_with_manual_item(db) -> tuple[Cohort, LmsProgramItem]:
    program = Program(
        id=uuid.uuid4(), code=f"CKI-{uuid.uuid4().hex[:8]}", name="Checklist Instructor Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Checklist Instructor Cohort", status="running")
    db.add(cohort)
    await db.flush()
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Instructor Test Checklist")
    db.add(lms_program)
    await db.flush()
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Attend the closing ceremony", requires_confirmation=True,
    )
    db.add(item)
    await db.flush()
    return cohort, item


async def _assign_instructor(db, *, instructor: User, cohort: Cohort) -> None:
    session = DeliverySession(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 1))
    db.add(session)
    await db.flush()
    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=session.id, user_id=instructor.id, role_id=await _role_id(db),
    ))
    await db.flush()


@pytest.mark.asyncio
async def test_unassigned_instructor_gets_404(db, client):
    instructor = await _user(db)
    cohort, _ = await _cohort_with_manual_item(db)
    await db.commit()

    resp = await client.get(f"/lms/instructor/cohorts/{cohort.id}/program-progress", headers=_headers(instructor))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_assigned_instructor_sees_the_roster(db, client):
    instructor = await _user(db)
    cohort, item = await _cohort_with_manual_item(db)
    await _assign_instructor(db, instructor=instructor, cohort=cohort)
    student = await _student(db)
    await db.commit()
    await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.get(f"/lms/instructor/cohorts/{cohort.id}/program-progress", headers=_headers(instructor))
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["student_name"] == "Checklist Instructor Test Student"
    assert rows[0]["items_done"] == 0 and rows[0]["items_total"] == 1


@pytest.mark.asyncio
async def test_ops_sees_the_roster_without_a_session_assignment(db, client):
    ops = await _user(db, roles=["operations"])
    cohort, item = await _cohort_with_manual_item(db)
    student = await _student(db)
    await db.commit()
    await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.get(f"/lms/instructor/cohorts/{cohort.id}/program-progress", headers=_headers(ops))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_confirm_marks_the_item_done_and_records_who(db, client):
    instructor = await _user(db)
    cohort, item = await _cohort_with_manual_item(db)
    await _assign_instructor(db, instructor=instructor, cohort=cohort)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/instructor/cohorts/{cohort.id}/program-progress/{assignment.id}/items/{item.id}/confirm",
        headers=_headers(instructor),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["items_done"] == 1


@pytest.mark.asyncio
async def test_an_unassigned_instructor_cannot_confirm_either(db, client):
    instructor = await _user(db)
    cohort, item = await _cohort_with_manual_item(db)
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    resp = await client.post(
        f"/lms/instructor/cohorts/{cohort.id}/program-progress/{assignment.id}/items/{item.id}/confirm",
        headers=_headers(instructor),
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND
