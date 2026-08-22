"""LMS Program checklist service layer (2026-08-21 redesign) —
resolve_cohort_program's override-vs-program resolution, assign_lms_program's
materialization (courses enrolled, mission runs assigned up front), and
certificate_gate_satisfied. Redis-free, HTTP-free.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.lms import Course, Enrollment
from app.models.lms.program import (
    LmsProgram, LmsProgramAssignment, LmsProgramCohortOverride, LmsProgramItem, LmsProgramItemProgress,
)
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms.program import assign_lms_program, certificate_gate_satisfied, resolve_cohort_program
from app.services.missions import decide_attempt


async def _author(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Checklist Author", email=f"author-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _program_and_cohort(db) -> tuple[Program, Cohort]:
    program = Program(
        id=uuid.uuid4(), code=f"CHK-{uuid.uuid4().hex[:8]}", name="Checklist Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Checklist Cohort", status="running")
    db.add(cohort)
    await db.flush()
    return program, cohort


async def _course(db, *, author) -> Course:
    course = Course(id=uuid.uuid4(), title=f"Course {uuid.uuid4().hex[:6]}", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    return course


async def _mission_with_variant(db, *, author) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Checklist Mission", slug=f"checklist-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published", team_policy="solo",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Cadet", position=1, points=10)
    db.add(variant)
    await db.flush()
    return mission, variant


async def _student(db) -> User:
    contact = Contact(
        id=uuid.uuid4(), full_name="Checklist Student", contact_roles=["student"],
        secondary_phones=[], preferred_language="en", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name="Checklist Student", email=f"stu-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(user)
    await db.flush()
    return user


# ── resolve_cohort_program ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_returns_none_for_a_cohort_with_no_checklist(db):
    _, cohort = await _program_and_cohort(db)
    await db.commit()
    assert await resolve_cohort_program(db, cohort.id) is None


@pytest.mark.asyncio
async def test_resolve_falls_back_to_the_program_level_checklist(db):
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    course = await _course(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Program Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    ))
    await db.commit()

    resolved = await resolve_cohort_program(db, cohort.id)
    assert resolved is not None
    resolved_program, items = resolved
    assert resolved_program.id == lms_program.id
    assert [i.course_id for i in items] == [course.id]


@pytest.mark.asyncio
async def test_cohort_override_wins_outright_over_the_program_checklist(db):
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    program_course = await _course(db, author=author)
    override_course = await _course(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Program Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=program_course.title, course_id=program_course.id,
    ))
    override = LmsProgramCohortOverride(id=uuid.uuid4(), cohort_id=cohort.id, lms_program_id=lms_program.id)
    db.add(override)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="cohort_override", owner_id=override.id, position=1,
        item_type="course", title=override_course.title, course_id=override_course.id,
    ))
    await db.commit()

    resolved = await resolve_cohort_program(db, cohort.id)
    _, items = resolved
    assert [i.course_id for i in items] == [override_course.id]  # program's course is NOT merged in


@pytest.mark.asyncio
async def test_an_empty_override_row_falls_back_to_the_program_checklist(db):
    """An override row with zero items of its own does not shadow the
    program's checklist — 'nearest level with any rows wins', not 'nearest
    level period'."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    course = await _course(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Program Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    ))
    db.add(LmsProgramCohortOverride(id=uuid.uuid4(), cohort_id=cohort.id, lms_program_id=lms_program.id))
    await db.commit()

    resolved = await resolve_cohort_program(db, cohort.id)
    _, items = resolved
    assert [i.course_id for i in items] == [course.id]


# ── assign_lms_program ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assign_is_a_noop_for_a_cohort_with_no_checklist(db):
    _, cohort = await _program_and_cohort(db)
    student = await _student(db)
    await db.commit()
    assert await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id) is None


@pytest.mark.asyncio
async def test_assign_enrolls_courses_and_assigns_mission_runs_immediately(db):
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    course = await _course(db, author=author)
    mission, variant = await _mission_with_variant(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Full Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    ))
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
    ))
    student = await _student(db)
    await db.commit()

    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    assert assignment is not None
    assert assignment.lms_program_id == lms_program.id

    enrollment = (await db.execute(select(Enrollment).where(Enrollment.user_id == student.id))).scalars().first()
    assert enrollment is not None and enrollment.course_id == course.id

    attempt = (await db.execute(select(MissionAttempt).where(MissionAttempt.user_id == student.id))).scalars().first()
    assert attempt is not None and attempt.mission_id == mission.id and attempt.cohort_id == cohort.id

    progress_rows = (await db.execute(
        select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == assignment.id)
    )).scalars().all()
    assert len(progress_rows) == 2  # one per item, materialized up front


@pytest.mark.asyncio
async def test_assign_is_idempotent_per_user_and_cohort(db):
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    course = await _course(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Idempotent Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    ))
    student = await _student(db)
    await db.commit()

    first = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    second = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    assert first.id == second.id

    rows = (await db.execute(
        select(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == student.id, LmsProgramAssignment.cohort_id == cohort.id,
        )
    )).scalars().all()
    assert len(rows) == 1


# ── certificate_gate_satisfied ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gate_is_satisfied_with_no_checklist_at_all(db):
    _, cohort = await _program_and_cohort(db)
    student = await _student(db)
    await db.commit()
    assert await certificate_gate_satisfied(db, cohort_id=cohort.id, user_id=student.id) is True


@pytest.mark.asyncio
async def test_gate_is_satisfied_when_certificate_required_is_false(db):
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    course = await _course(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Ungated Checklist", certificate_required=False)
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    ))
    student = await _student(db)
    await db.commit()
    await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    assert await certificate_gate_satisfied(db, cohort_id=cohort.id, user_id=student.id) is True


@pytest.mark.asyncio
async def test_gate_blocks_until_a_required_mission_run_item_passes(db):
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Gated Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
    ))
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    assert await certificate_gate_satisfied(db, cohort_id=cohort.id, user_id=student.id) is False

    attempt = (await db.execute(select(MissionAttempt).where(MissionAttempt.user_id == student.id))).scalars().first()
    await decide_attempt(db, attempt=attempt, passed=True)
    await db.commit()

    assert await certificate_gate_satisfied(db, cohort_id=cohort.id, user_id=student.id) is True


@pytest.mark.asyncio
async def test_gate_ignores_optional_items(db):
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    course = await _course(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Optional Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="article", title="Read this", optional=True, external_url="https://example.com/read",
    ))
    student = await _student(db)
    await db.commit()
    await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    assert await certificate_gate_satisfied(db, cohort_id=cohort.id, user_id=student.id) is True


@pytest.mark.asyncio
async def test_gate_blocks_a_student_with_no_assignment_when_required(db):
    """A checklist that requires it, with a student who was never assigned
    (e.g. account created before the checklist existed) is not satisfied —
    absence is not completion."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    course = await _course(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Strict Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    ))
    student = await _student(db)
    await db.commit()

    assert await certificate_gate_satisfied(db, cohort_id=cohort.id, user_id=student.id) is False
