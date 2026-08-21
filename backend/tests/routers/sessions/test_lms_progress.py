"""LM1-10 — GET /sessions/{session_id}/lms-progress.

Reuses the exact roster scoping test_delivery_router.py already exercises
(unassigned instructor -> 404, ops always allowed) and layers the LMS side on
top: a student with a linked account and curriculum enrollment reports
module/quiz progress; a student with no LMS account reports
has_lms_account=False and an empty course list, not an error.
"""

import uuid
from datetime import date

import httpx
import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.session import get_db
from app.main import app
from app.models.lms import Course
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms import enroll
from app.services.sessions.registration import register


@pytest.fixture
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _role_id(db, name: str = "Lead Facilitator"):
    return await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))


async def _make_cohort_with_session(db, **overrides) -> tuple[Cohort, Session]:
    program = Program(
        id=uuid.uuid4(), code=f"LMSPROG-{uuid.uuid4().hex[:8]}", name="LMS Progress Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="LMS Progress Test Cohort",
        status="registration_open", visibility="public",
    )
    db.add(cohort)
    await db.flush()
    defaults = dict(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 20))
    defaults.update(overrides)
    session = Session(**defaults)
    db.add(session)
    await db.flush()
    return program, cohort, session


async def _user(db, *, roles) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Progress Router User", email=f"lms-prog-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=roles, status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _assign(db, session: Session, user_id) -> None:
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=user_id, role_id=await _role_id(db)))
    await db.flush()


@pytest.mark.asyncio
async def test_unassigned_instructor_gets_404(db, client):
    _, _, session = await _make_cohort_with_session(db)
    instructor = await _user(db, roles=["instructor"])
    await db.commit()

    resp = await client.get(f"/sessions/{session.id}/lms-progress", headers=_headers(instructor))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ops_sees_progress_without_an_assignment(db, client):
    program, cohort, session = await _make_cohort_with_session(db)
    ops = await _user(db, roles=["operations"])

    author = await _user(db, roles=["operations"])
    course = Course(id=uuid.uuid4(), title="Curriculum Course", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Progress Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    ))

    contact = Contact(
        id=uuid.uuid4(), full_name="Progress Student", contact_roles=["student"],
        secondary_phones=[], preferred_language="ar", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    registration = await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="desk")

    student_account = User(
        id=uuid.uuid4(), full_name="Progress Student", email="progress.student@example.com",
        password_hash="x", roles=["student"], contact_id=contact.id, status="active",
    )
    db.add(student_account)
    await db.flush()
    await enroll(
        db, user_id=student_account.id, course_id=course.id, source="registration",
        program_id=program.id, registration_id=registration.id,
    )
    await db.commit()

    resp = await client.get(f"/sessions/{session.id}/lms-progress", headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["program_name"] == "LMS Progress Test Program"
    assert len(body["students"]) == 1

    student = body["students"][0]
    assert student["student_name"] == "Progress Student"
    assert student["has_lms_account"] is True
    assert len(student["courses"]) == 1
    course_progress = student["courses"][0]
    assert course_progress["course_id"] == str(course.id)
    assert course_progress["course_title"] == "Curriculum Course"
    # A course with zero authored modules is vacuously "completed" — the
    # same derived-completion rule LM1-2's course_completion() documents
    # ("every module done"; no modules trivially satisfies that).
    assert course_progress["completed"] is True
    assert course_progress["modules"] == []  # no modules authored yet
    assert course_progress["quizzes"] == []


@pytest.mark.asyncio
async def test_assigned_instructor_sees_progress_and_student_without_account_is_flagged(db, client):
    program, cohort, session = await _make_cohort_with_session(db)
    instructor = await _user(db, roles=["instructor"])
    await _assign(db, session, instructor.id)

    contact = Contact(
        id=uuid.uuid4(), full_name="No Account Student", contact_roles=["student"],
        secondary_phones=[], preferred_language="ar", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="desk")
    await db.commit()

    resp = await client.get(f"/sessions/{session.id}/lms-progress", headers=_headers(instructor))
    assert resp.status_code == 200, resp.text
    student = resp.json()["students"][0]
    assert student["has_lms_account"] is False
    assert student["courses"] == []
