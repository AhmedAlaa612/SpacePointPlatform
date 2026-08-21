"""P4-3 (LMS Phase 2 Stage 4, 2026-08-10) — GET /lms/my-programs: the cohort
view a student cannot currently see at all. Redis-free.
"""

import uuid
from datetime import date

import pytest

from app.core.security import create_access_token
from app.models.lms import Course, CourseModule, ModuleItem
from app.models.lms.program import LmsProgram, LmsProgramCohortOverride, LmsProgramItem
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session as DeliverySession
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms import enroll, item_progress


async def _author(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Author", email=f"author-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.mark.asyncio
async def test_my_programs_is_empty_for_a_user_with_no_contact(db, client):
    student = User(
        id=uuid.uuid4(), full_name="No Contact", email=f"nc-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active",
    )
    db.add(student)
    await db.commit()

    resp = await client.get("/lms/my-programs", headers=_headers(student))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_my_programs_composes_dates_location_instructor_attendance_courses(db, client):
    author = await _author(db)
    instructor = User(
        id=uuid.uuid4(), full_name="Lead Instructor", email=f"li-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["instructor"], status="active",
    )
    db.add(instructor)
    await db.flush()

    program = Program(
        id=uuid.uuid4(), code=f"MP-{uuid.uuid4().hex[:8]}", name="My Programs Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="My Programs Cohort", status="running",
        starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 5),
        location="SpacePoint HQ", location_map_url="https://maps.example/hq",
        lead_instructor_user_id=instructor.id,
    )
    db.add(cohort)
    await db.flush()

    course = Course(id=uuid.uuid4(), title="Orbital Mechanics", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="text", content={"body": "x"})
    db.add(item)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="My Programs Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title="Orbital Mechanics", course_id=course.id,
    ))
    await db.flush()

    contact = Contact(id=uuid.uuid4(), full_name="My Programs Student", contact_roles=["student"])
    db.add(contact)
    await db.flush()
    student = User(
        id=uuid.uuid4(), full_name="My Programs Student", email=f"mp-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(student)
    await db.flush()
    registration = Registration(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id, status="attended",
        ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="waived",
    )
    db.add(registration)
    await db.flush()

    delivery_session = DeliverySession(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 1))
    db.add(delivery_session)
    await db.flush()
    db.add(AttendanceRecord(
        id=uuid.uuid4(), registration_id=registration.id, session_id=delivery_session.id,
        att_status="present", recorded_by_user_id=author.id,
    ))
    await enroll(db, user_id=student.id, course_id=course.id, source="registration", registration_id=registration.id)
    await item_progress(db, user_id=student.id, item_id=item.id, action="text-viewed")
    await db.commit()

    resp = await client.get("/lms/my-programs", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    programs = resp.json()
    assert len(programs) == 1
    program_out = programs[0]

    assert program_out["program_name"] == "My Programs Program"
    assert program_out["cohort_name"] == "My Programs Cohort"
    assert program_out["starts_on"] == "2026-09-01"
    assert program_out["ends_on"] == "2026-09-05"
    assert program_out["location_name"] == "SpacePoint HQ"
    assert program_out["instructor_name"] == "Lead Instructor"
    assert program_out["attended_sessions"] == 1
    assert program_out["total_sessions"] == 1
    assert program_out["missions"] == []

    assert len(program_out["courses"]) == 1
    course_out = program_out["courses"][0]
    assert course_out["title"] == "Orbital Mechanics"
    assert course_out["enrolled"] is True
    assert course_out["progress_pct"] == 100


@pytest.mark.asyncio
async def test_my_programs_respects_cohort_curriculum_override(db, client):
    author = await _author(db)
    program = Program(
        id=uuid.uuid4(), code=f"MPO-{uuid.uuid4().hex[:8]}", name="Override Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Override Cohort", status="running")
    db.add(cohort)
    await db.flush()

    program_course = Course(id=uuid.uuid4(), title="Program Course", created_by=author.id, is_published=True)
    cohort_course = Course(id=uuid.uuid4(), title="Cohort Course", created_by=author.id, is_published=True)
    db.add_all([program_course, cohort_course])
    await db.flush()
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Override Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title="Program Course", course_id=program_course.id,
    ))
    override = LmsProgramCohortOverride(id=uuid.uuid4(), cohort_id=cohort.id, lms_program_id=lms_program.id)
    db.add(override)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="cohort_override", owner_id=override.id, position=1,
        item_type="course", title="Cohort Course", course_id=cohort_course.id,
    ))
    await db.flush()

    contact = Contact(id=uuid.uuid4(), full_name="Override Student", contact_roles=["student"])
    db.add(contact)
    await db.flush()
    student = User(
        id=uuid.uuid4(), full_name="Override Student", email=f"ov-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(student)
    await db.flush()
    db.add(Registration(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id, status="registered",
        ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="waived",
    ))
    await db.commit()

    resp = await client.get("/lms/my-programs", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    titles = {c["title"] for c in resp.json()[0]["courses"]}
    assert titles == {"Cohort Course"}
