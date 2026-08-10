"""P4-1/P4-2 (LMS Phase 2 Stage 4, 2026-08-10) — cohort curriculum
resolution (override, never merge) and reconciliation (a curriculum
change reaches everyone already registered, not just future
registrations). Redis-free, HTTP-free.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.lms import CohortCurriculum, Course, Enrollment, ProgramCurriculum
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms.curriculum import (
    enroll_in_cohort_curriculum,
    reconcile_cohort_enrollments,
    reconcile_cohorts_inheriting_program,
    resolve_cohort_curriculum,
)


async def _author(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Author", email=f"author-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _program_cohort(db) -> tuple[Program, Cohort]:
    program = Program(
        id=uuid.uuid4(), code=f"CUR-{uuid.uuid4().hex[:8]}", name="Curriculum Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Curriculum Cohort", status="running")
    db.add(cohort)
    await db.flush()
    return program, cohort


async def _course(db, *, author) -> Course:
    course = Course(id=uuid.uuid4(), title=f"Course {uuid.uuid4().hex[:8]}", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    return course


async def _registered_student(db, *, cohort) -> tuple[Contact, User, Registration]:
    contact = Contact(id=uuid.uuid4(), full_name="Student", contact_roles=["student"])
    db.add(contact)
    await db.flush()
    student = User(
        id=uuid.uuid4(), full_name="Student", email=f"student-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(student)
    await db.flush()
    registration = Registration(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id, status="registered",
        ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="waived",
    )
    db.add(registration)
    await db.flush()
    return contact, student, registration


# ── resolve_cohort_curriculum: override, never merge ────────────────────────

@pytest.mark.asyncio
async def test_resolves_to_program_curriculum_with_no_cohort_override(db):
    author = await _author(db)
    program, cohort = await _program_cohort(db)
    course = await _course(db, author=author)
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=course.id, position=1))
    await db.commit()

    result = await resolve_cohort_curriculum(db, cohort.id)
    assert result == [course.id]


@pytest.mark.asyncio
async def test_cohort_override_wins_outright_not_merged(db):
    """A cohort with its own curriculum rows does not inherit the program's
    at all — the program course must NOT appear alongside the cohort one."""
    author = await _author(db)
    program, cohort = await _program_cohort(db)
    program_course = await _course(db, author=author)
    cohort_course = await _course(db, author=author)
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=program_course.id, position=1))
    db.add(CohortCurriculum(id=uuid.uuid4(), cohort_id=cohort.id, course_id=cohort_course.id, position=1))
    await db.commit()

    result = await resolve_cohort_curriculum(db, cohort.id)
    assert result == [cohort_course.id]


@pytest.mark.asyncio
async def test_cohort_curriculum_can_remove_a_program_course_for_one_cohort(db):
    """The whole point of override-not-merge: a cohort can teach FEWER
    courses than its program's default curriculum."""
    author = await _author(db)
    program, cohort = await _program_cohort(db)
    kept = await _course(db, author=author)
    dropped = await _course(db, author=author)
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=kept.id, position=1))
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=dropped.id, position=2))
    db.add(CohortCurriculum(id=uuid.uuid4(), cohort_id=cohort.id, course_id=kept.id, position=1))
    await db.commit()

    result = await resolve_cohort_curriculum(db, cohort.id)
    assert result == [kept.id]


# ── reconcile_cohort_enrollments: reaches everyone already registered ───────

@pytest.mark.asyncio
async def test_reconcile_enrolls_every_registered_student_in_a_newly_added_course(db):
    author = await _author(db)
    program, cohort = await _program_cohort(db)
    original = await _course(db, author=author)
    added_later = await _course(db, author=author)
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=original.id, position=1))
    await db.commit()

    _contact_a, student_a, reg_a = await _registered_student(db, cohort=cohort)
    _contact_b, student_b, reg_b = await _registered_student(db, cohort=cohort)
    await enroll_in_cohort_curriculum(db, user_id=student_a.id, cohort_id=cohort.id, registration_id=reg_a.id)
    await enroll_in_cohort_curriculum(db, user_id=student_b.id, cohort_id=cohort.id, registration_id=reg_b.id)
    await db.commit()

    # A course is added to the curriculum AFTER both students already registered.
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=added_later.id, position=2))
    await db.commit()

    created = await reconcile_cohort_enrollments(db, cohort.id)
    assert created == 2  # one new enrollment per already-registered student

    enrolled_courses_a = set((await db.execute(
        select(Enrollment.course_id).where(Enrollment.user_id == student_a.id)
    )).scalars().all())
    assert enrolled_courses_a == {original.id, added_later.id}


@pytest.mark.asyncio
async def test_reconcile_is_idempotent(db):
    author = await _author(db)
    program, cohort = await _program_cohort(db)
    course = await _course(db, author=author)
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=course.id, position=1))
    await db.commit()
    _contact, student, reg = await _registered_student(db, cohort=cohort)
    await enroll_in_cohort_curriculum(db, user_id=student.id, cohort_id=cohort.id, registration_id=reg.id)
    await db.commit()

    first = await reconcile_cohort_enrollments(db, cohort.id)
    second = await reconcile_cohort_enrollments(db, cohort.id)
    assert first == 0  # already enrolled from registration time
    assert second == 0


@pytest.mark.asyncio
async def test_reconcile_skips_a_registered_contact_with_no_lms_account(db):
    author = await _author(db)
    program, cohort = await _program_cohort(db)
    course = await _course(db, author=author)
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=course.id, position=1))
    contact = Contact(id=uuid.uuid4(), full_name="No Account", contact_roles=["student"])
    db.add(contact)
    await db.flush()
    db.add(Registration(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id, status="registered",
        ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="waived",
    ))
    await db.commit()

    created = await reconcile_cohort_enrollments(db, cohort.id)
    assert created == 0  # nothing to raise, nothing to enroll


# ── fan-out across cohorts inheriting a program's curriculum ────────────────

@pytest.mark.asyncio
async def test_fan_out_reaches_cohorts_without_their_own_override_only(db):
    author = await _author(db)
    program, inheriting_cohort = await _program_cohort(db)
    overriding_cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Overriding Cohort", status="running")
    db.add(overriding_cohort)
    await db.flush()

    shared_course = await _course(db, author=author)
    override_course = await _course(db, author=author)
    db.add(CohortCurriculum(id=uuid.uuid4(), cohort_id=overriding_cohort.id, course_id=override_course.id, position=1))
    await db.commit()

    _c1, inheriting_student, reg1 = await _registered_student(db, cohort=inheriting_cohort)
    _c2, overriding_student, reg2 = await _registered_student(db, cohort=overriding_cohort)
    await db.commit()

    # Program curriculum gains a course AFTER both cohorts have registrants.
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=shared_course.id, position=1))
    await db.commit()

    await reconcile_cohorts_inheriting_program(db, program.id)

    inheriting_enrollments = set((await db.execute(
        select(Enrollment.course_id).where(Enrollment.user_id == inheriting_student.id)
    )).scalars().all())
    overriding_enrollments = set((await db.execute(
        select(Enrollment.course_id).where(Enrollment.user_id == overriding_student.id)
    )).scalars().all())

    assert inheriting_enrollments == {shared_course.id}
    assert overriding_enrollments == set()  # has its own curriculum, untouched by the program change
