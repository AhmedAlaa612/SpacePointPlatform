"""LM1-7 service tests — get_or_create_student_account, curriculum
auto-enroll, and enrollment status following registration status. Direct
service calls (no HTTP layer) — the router wiring is covered separately in
tests/routers/sessions/test_desk_register_lms.py.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.lms import Course, Enrollment, ProgramCurriculum
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms.ops_integration import (
    deactivate_registration_enrollments,
    enroll_in_program_curriculum,
    get_or_create_student_account,
    sync_registration_lms,
)


async def _contact(db, *, email="student@example.com", full_name="Ada Lovelace") -> Contact:
    contact = Contact(id=uuid.uuid4(), full_name=full_name, contact_roles=["student"], email=email)
    db.add(contact)
    await db.flush()
    return contact


async def _program_cohort(db) -> tuple[Program, Cohort]:
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="C", status="running")
    db.add(cohort)
    await db.flush()
    return program, cohort


async def _course(db, *, author) -> Course:
    course = Course(id=uuid.uuid4(), title="Course", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    return course


async def _registration(db, *, contact, cohort) -> Registration:
    reg = Registration(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id,
        status="registered", ticket_token=uuid.uuid4().hex, registered_via="desk",
        payment_status="waived",
    )
    db.add(reg)
    await db.flush()
    return reg


async def _author(db) -> User:
    author = User(
        id=uuid.uuid4(), full_name="Author", email=f"author-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(author)
    await db.flush()
    return author


# ── get_or_create_student_account ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_creates_a_new_student_account_with_a_random_password(db):
    contact = await _contact(db)
    await db.commit()

    user, created = await get_or_create_student_account(db, contact.id)
    assert created is True
    assert user.contact_id == contact.id
    assert user.roles == ["student"]
    assert user.must_change_password is True
    assert user.email == contact.email


@pytest.mark.asyncio
async def test_reuses_an_existing_account_linked_to_the_contact_and_adds_student_role(db):
    contact = await _contact(db)
    existing = User(
        id=uuid.uuid4(), full_name="Existing", email="existing@example.com",
        password_hash="x", roles=["instructor"], contact_id=contact.id, status="active",
    )
    db.add(existing)
    await db.commit()

    user, created = await get_or_create_student_account(db, contact.id)
    assert created is False
    assert user.id == existing.id
    assert set(user.role_values) == {"instructor", "student"}


@pytest.mark.asyncio
async def test_no_email_skips_account_creation_without_raising(db):
    contact = await _contact(db, email=None)
    await db.commit()

    user, created = await get_or_create_student_account(db, contact.id)
    assert user is None and created is False


@pytest.mark.asyncio
async def test_email_collision_with_a_different_account_skips_without_raising(db):
    contact = await _contact(db, email="taken@example.com")
    other = User(
        id=uuid.uuid4(), full_name="Someone Else", email="taken@example.com",
        password_hash="x", roles=["ambassador"], status="active",
    )
    db.add(other)
    await db.commit()

    user, created = await get_or_create_student_account(db, contact.id)
    assert user is None and created is False


# ── enroll_in_program_curriculum ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enrolls_in_every_curriculum_course(db):
    author = await _author(db)
    program, cohort = await _program_cohort(db)
    course_a = await _course(db, author=author)
    course_b = await _course(db, author=author)
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=course_a.id, position=1))
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=course_b.id, position=2))
    contact = await _contact(db)
    student = User(
        id=uuid.uuid4(), full_name="S", email="s@example.com", password_hash="x",
        roles=["student"], contact_id=contact.id, status="active",
    )
    db.add(student)
    registration = await _registration(db, contact=contact, cohort=cohort)
    await db.commit()

    enrollments = await enroll_in_program_curriculum(
        db, user_id=student.id, program_id=program.id, registration_id=registration.id,
    )
    assert {e.course_id for e in enrollments} == {course_a.id, course_b.id}
    assert all(e.source == "registration" and e.registration_id == registration.id for e in enrollments)


# ── sync_registration_lms + deactivate ──────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_registration_lms_creates_account_and_enrolls(db):
    author = await _author(db)
    program, cohort = await _program_cohort(db)
    course = await _course(db, author=author)
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=course.id, position=1))
    contact = await _contact(db)
    registration = await _registration(db, contact=contact, cohort=cohort)
    await db.commit()

    user = await sync_registration_lms(db, registration=registration, cohort=cohort, create_account=True)
    assert user is not None and user.contact_id == contact.id

    rows = (await db.execute(select(Enrollment).where(Enrollment.user_id == user.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].course_id == course.id and rows[0].registration_id == registration.id


@pytest.mark.asyncio
async def test_sync_registration_lms_noop_when_create_account_false(db):
    program, cohort = await _program_cohort(db)
    contact = await _contact(db)
    registration = await _registration(db, contact=contact, cohort=cohort)
    await db.commit()

    user = await sync_registration_lms(db, registration=registration, cohort=cohort, create_account=False)
    assert user is None
    assert (await db.execute(select(User).where(User.contact_id == contact.id))).first() is None


@pytest.mark.asyncio
async def test_deactivate_registration_enrollments_flips_active_rows_only(db):
    author = await _author(db)
    program, cohort = await _program_cohort(db)
    course = await _course(db, author=author)
    contact = await _contact(db)
    registration = await _registration(db, contact=contact, cohort=cohort)
    student = User(
        id=uuid.uuid4(), full_name="S", email="s2@example.com", password_hash="x",
        roles=["student"], contact_id=contact.id, status="active",
    )
    db.add(student)
    await db.flush()
    enrollment = Enrollment(
        id=uuid.uuid4(), user_id=student.id, course_id=course.id, source="registration",
        program_id=program.id, registration_id=registration.id, status="active",
    )
    db.add(enrollment)
    await db.commit()

    await deactivate_registration_enrollments(db, registration.id)
    await db.commit()
    await db.refresh(enrollment)
    assert enrollment.status == "inactive"
