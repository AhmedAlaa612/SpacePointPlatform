"""LM1-7 — the desk-registration/cancel wiring to the LMS: "Create LMS
account" defaults on, creates a student account and assigns the program's
LMS Program checklist (2026-08-21 — enrolls every course item), and
cancelling a registration deactivates the enrollments it started (D4). Uses
the same `_make_cohort` shape as test_registration_desk.py.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.lms import Course, Enrollment
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.user import User


async def _attach_course_checklist(db, *, program: Program, course: Course) -> None:
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Desk Test Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    ))


async def _make_cohort(db, **overrides) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"LMS-DESK-{uuid.uuid4().hex[:8]}", name="LMS Desk Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    defaults = dict(
        id=uuid.uuid4(), program_id=program.id, name="LMS Desk Test Cohort",
        status="registration_open", visibility="public",
    )
    defaults.update(overrides)
    cohort = Cohort(**defaults)
    db.add(cohort)
    await db.flush()
    return program, cohort


async def _author(db) -> User:
    author = User(
        id=uuid.uuid4(), full_name="Author", email=f"author-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(author)
    await db.flush()
    return author


@pytest.mark.asyncio
async def test_desk_register_creates_lms_account_and_enrolls_by_default(db, client, operations_headers):
    author = await _author(db)
    program, cohort = await _make_cohort(db)
    course = Course(id=uuid.uuid4(), title="Curriculum Course", created_by=author.id, is_published=True)
    db.add(course)
    await _attach_course_checklist(db, program=program, course=course)
    await db.commit()

    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/registrations",
        json={
            "student_name": "LMS Desk Student", "email": "lms.desk.student@example.com",
            "phone": "050 111 2222", "city": "Dubai",
        },
        headers=operations_headers,
    )
    assert resp.status_code == 201, resp.text

    contact = (await db.execute(
        select(Contact).where(Contact.email == "lms.desk.student@example.com")
    )).scalars().first()
    student = (await db.execute(select(User).where(User.contact_id == contact.id))).scalars().first()
    assert student is not None
    assert "student" in student.role_values
    assert student.must_change_password is True

    enrollments = (await db.execute(select(Enrollment).where(Enrollment.user_id == student.id))).scalars().all()
    assert [e.course_id for e in enrollments] == [course.id]
    assert enrollments[0].source == "registration" and enrollments[0].status == "active"


@pytest.mark.asyncio
async def test_desk_register_can_opt_out_of_lms_account(db, client, operations_headers):
    program, cohort = await _make_cohort(db)
    await db.commit()

    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/registrations",
        json={
            "student_name": "No LMS Student", "email": "no.lms.student@example.com",
            "phone": "050 333 4444", "city": "Dubai", "create_lms_account": False,
        },
        headers=operations_headers,
    )
    assert resp.status_code == 201, resp.text

    contact = (await db.execute(
        select(Contact).where(Contact.email == "no.lms.student@example.com")
    )).scalars().first()
    student = (await db.execute(select(User).where(User.contact_id == contact.id))).first()
    assert student is None


@pytest.mark.asyncio
async def test_cancel_registration_deactivates_its_lms_enrollments(db, client, operations_headers):
    author = await _author(db)
    program, cohort = await _make_cohort(db)
    course = Course(id=uuid.uuid4(), title="Curriculum Course", created_by=author.id, is_published=True)
    db.add(course)
    await _attach_course_checklist(db, program=program, course=course)
    await db.commit()

    created = await client.post(
        f"/sessions/cohorts/{cohort.id}/registrations",
        json={
            "student_name": "Cancel Me", "email": "cancel.me@example.com",
            "phone": "050 555 6666", "city": "Dubai",
        },
        headers=operations_headers,
    )
    registration_id = created.json()["id"]

    contact = (await db.execute(select(Contact).where(Contact.email == "cancel.me@example.com"))).scalars().first()
    student = (await db.execute(select(User).where(User.contact_id == contact.id))).scalars().first()
    enrollment = (await db.execute(select(Enrollment).where(Enrollment.user_id == student.id))).scalars().first()
    assert enrollment.status == "active"

    cancel = await client.post(f"/sessions/registrations/{registration_id}/cancel", headers=operations_headers)
    assert cancel.status_code == 200

    await db.refresh(enrollment)
    assert enrollment.status == "inactive"
