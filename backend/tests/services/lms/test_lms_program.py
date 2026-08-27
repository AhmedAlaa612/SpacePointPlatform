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
from app.services.lms.program import (
    assign_lms_program, certificate_gate_satisfied, fork_cohort_override, resolve_cohort_program,
    sync_cohort_assignments, sync_program_assignments,
)
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


# ── sync_program_assignments / sync_cohort_assignments (backfill) ───────────

@pytest.mark.asyncio
async def test_adding_a_program_item_backfills_already_assigned_students(db):
    """The reported bug: ops adds a checklist step after students are
    already assigned, and it never reaches them without this backfill."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    course = await _course(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Late Addition Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    ))
    student = await _student(db)
    await db.commit()

    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()
    assert len((await db.execute(
        select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == assignment.id)
    )).scalars().all()) == 1

    new_mission, new_variant = await _mission_with_variant(db, author=author)
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="mission_run", title=new_mission.title, mission_id=new_mission.id, variant_id=new_variant.id,
    ))
    await db.commit()

    added = await sync_program_assignments(db, lms_program_id=lms_program.id)
    await db.commit()
    assert added == 1

    progress_rows = (await db.execute(
        select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == assignment.id)
    )).scalars().all()
    assert len(progress_rows) == 2
    new_row = next(p for p in progress_rows if p.mission_attempt_id is not None)
    attempt = (await db.execute(
        select(MissionAttempt).where(MissionAttempt.id == new_row.mission_attempt_id)
    )).scalar_one()
    assert attempt.mission_id == new_mission.id  # the mission run's own side effect ran too

    # Safe to call again — nothing missing now.
    assert await sync_program_assignments(db, lms_program_id=lms_program.id) == 0


@pytest.mark.asyncio
async def test_backfill_respects_a_cohort_override_that_already_won(db):
    """A cohort with its own override must not get an item added to the
    *program's* checklist — resolve_cohort_program says the override
    still wins there, so sync must no-op for that cohort."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    program_course = await _course(db, author=author)
    override_course = await _course(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Overridden Checklist")
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
    student = await _student(db)
    await db.commit()

    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    new_course = await _course(db, author=author)
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="course", title=new_course.title, course_id=new_course.id,
    ))
    await db.commit()

    assert await sync_program_assignments(db, lms_program_id=lms_program.id) == 0
    progress_rows = (await db.execute(
        select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == assignment.id)
    )).scalars().all()
    assert len(progress_rows) == 1  # still just the override's own course, nothing from the program


@pytest.mark.asyncio
async def test_adding_a_cohort_override_item_backfills_that_cohort_only(db):
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    course = await _course(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Cohort Checklist")
    db.add(lms_program)
    await db.flush()
    override = LmsProgramCohortOverride(id=uuid.uuid4(), cohort_id=cohort.id, lms_program_id=lms_program.id)
    db.add(override)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="cohort_override", owner_id=override.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    ))
    student = await _student(db)
    await db.commit()

    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    new_course = await _course(db, author=author)
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="cohort_override", owner_id=override.id, position=2,
        item_type="course", title=new_course.title, course_id=new_course.id,
    ))
    await db.commit()

    added = await sync_cohort_assignments(db, cohort_id=cohort.id)
    await db.commit()
    assert added == 1

    progress_rows = (await db.execute(
        select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == assignment.id)
    )).scalars().all()
    assert len(progress_rows) == 2


@pytest.mark.asyncio
async def test_forking_a_cohort_override_repoints_existing_progress_not_duplicates_it(db):
    """Editing an "inherited" item forks the program's items into the
    cohort's own override with brand-new item ids (fork_cohort_override).
    An already-assigned student's progress row pointed at the ORIGINAL
    program item — it must be repointed onto the fork's copy, not left
    stale alongside a second, duplicate row for the same item."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    course = await _course(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Forked Checklist")
    db.add(lms_program)
    await db.flush()
    original_item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    )
    db.add(original_item)
    student = await _student(db)
    await db.commit()

    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()
    before = (await db.execute(
        select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == assignment.id)
    )).scalars().one()
    assert before.item_id == original_item.id
    before_progress_id = before.id
    before.status = "done"  # the student had already made real progress before the fork
    await db.commit()

    forked = await fork_cohort_override(db, cohort_id=cohort.id)
    await db.commit()
    assert forked is not None
    _override, id_map = forked
    assert original_item.id in id_map

    rows = (await db.execute(
        select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == assignment.id)
    )).scalars().all()
    assert len(rows) == 1  # repointed in place, never duplicated
    assert rows[0].id == before_progress_id  # same row
    assert rows[0].item_id == id_map[original_item.id]  # now pointing at the fork's copy
    assert rows[0].status == "done"  # the student's real progress survived the fork


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
