"""LMS Program checklist service layer (2026-08-21 redesign) —
resolve_cohort_program's override-vs-program resolution, assign_lms_program's
materialization (courses enrolled, mission runs assigned up front), and
certificate_gate_satisfied. Redis-free, HTTP-free.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.lms import Course, Enrollment
from app.models.lms.program import (
    LmsProgram, LmsProgramAssignment, LmsProgramCohortOverride, LmsProgramItem, LmsProgramItemProgress,
    LmsProgramTeamItemProgress,
)
from app.services.teams import create_team, join_team
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.user import User
from app.schemas.lms_admin import LmsProgramItemIn
from app.services.lms.program import (
    assign_lms_program, assignment_item_detail, certificate_gate_satisfied, fork_cohort_override,
    get_student_checklist, guard_locked_submission_scope, resolve_cohort_program, sync_assignment_items,
    sync_cohort_assignments, sync_program_assignments, sync_team_mission_runs, team_mission_run_items,
    validate_item_payload, validate_item_refs,
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


async def _mission_with_variant(db, *, author, team_policy="solo") -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Checklist Mission", slug=f"checklist-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published", team_policy=team_policy,
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
async def test_assign_lms_program_shares_one_attempt_via_the_team_row(db):
    """Phase 2/3 (2026-09): a team-scoped mission_run item's shared
    MissionAttempt lives on the ONE LmsProgramTeamItemProgress row for
    (item, team) — not duplicated onto every teammate's own individual
    LmsProgramItemProgress row, which stays a never-read/written
    placeholder for a team-scoped item, same as any other team-scoped
    type. The first teammate assigned creates the attempt; the second
    finds it already set and reuses it."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author, team_policy="team")
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Team Mission Checklist")
    db.add(lms_program)
    await db.flush()
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
        scope="team",
    )
    db.add(item)
    await db.flush()
    alice = await _student(db)
    bob = await _student(db)
    team = await create_team(db, name="Radio Team", created_by=alice.id, cohort_id=cohort.id, member_ids=[bob.id])
    await db.commit()

    alice_assignment = await assign_lms_program(db, user_id=alice.id, cohort_id=cohort.id)
    bob_assignment = await assign_lms_program(db, user_id=bob.id, cohort_id=cohort.id)
    await db.commit()

    # Neither teammate's own individual row ever gets an attempt id — it's
    # a placeholder, exactly like a team-scoped submission item's is.
    alice_progress = (await db.execute(
        select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == alice_assignment.id)
    )).scalars().one()
    bob_progress = (await db.execute(
        select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == bob_assignment.id)
    )).scalars().one()
    assert alice_progress.mission_attempt_id is None
    assert bob_progress.mission_attempt_id is None

    team_progress = (await db.execute(
        select(LmsProgramTeamItemProgress).where(
            LmsProgramTeamItemProgress.item_id == item.id, LmsProgramTeamItemProgress.team_id == team.id,
        )
    )).scalars().one()
    assert team_progress.mission_attempt_id is not None

    attempt = (await db.execute(
        select(MissionAttempt).where(MissionAttempt.id == team_progress.mission_attempt_id)
    )).scalar_one()
    assert attempt.team_id == team.id
    assert attempt.user_id is None


@pytest.mark.asyncio
async def test_get_student_checklist_surfaces_the_teams_attempt_to_every_teammate(db):
    """Regression: get_student_checklist used to serialize
    `mission_attempt_id` straight off the caller's own individual
    progress row — for a team-scoped item that row is always None now
    (the attempt lives on the team row instead), so every teammate's own
    checklist would have shown their mission run as un-clickable, unable
    to navigate into the design page at all."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author, team_policy="team")
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Team Checklist Read Test")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
        scope="team",
    ))
    alice = await _student(db)
    bob = await _student(db)
    await create_team(db, name="Checklist Read Team", created_by=alice.id, cohort_id=cohort.id, member_ids=[bob.id])
    await db.commit()
    alice_assignment = await assign_lms_program(db, user_id=alice.id, cohort_id=cohort.id)
    bob_assignment = await assign_lms_program(db, user_id=bob.id, cohort_id=cohort.id)
    await db.commit()

    alice_checklist = await get_student_checklist(db, assignment_id=alice_assignment.id, user_id=alice.id)
    bob_checklist = await get_student_checklist(db, assignment_id=bob_assignment.id, user_id=bob.id)
    alice_item = alice_checklist["items"][0]
    bob_item = bob_checklist["items"][0]
    assert alice_item["mission_attempt_id"] is not None
    assert alice_item["mission_attempt_id"] == bob_item["mission_attempt_id"]


@pytest.mark.asyncio
async def test_assignment_item_detail_surfaces_the_teams_attempt_for_ops(db):
    """Regression: same bug as above, on the ops-facing Progress panel
    drill-in — 'View run' depends on this mission_attempt_id being
    populated to know which attempt to open."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author, team_policy="team")
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Ops Detail Read Test")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
        scope="team",
    ))
    alice = await _student(db)
    bob = await _student(db)
    await create_team(db, name="Ops Detail Team", created_by=alice.id, cohort_id=cohort.id, member_ids=[bob.id])
    await db.commit()
    alice_assignment = await assign_lms_program(db, user_id=alice.id, cohort_id=cohort.id)
    await assign_lms_program(db, user_id=bob.id, cohort_id=cohort.id)
    await db.commit()

    details = await assignment_item_detail(db, assignment_id=alice_assignment.id)
    assert details is not None
    assert len(details) == 1
    assert details[0]["mission_attempt_id"] is not None
    # A viewer needs to know which kind of run this is (design vs.
    # ground_station vs. ...) to decide whether DesignRunDetail can even
    # render it — a ground_station attempt has no Design row to read.
    assert details[0]["mission_kind"] == mission.kind


@pytest.mark.asyncio
async def test_assign_lms_program_skips_the_attempt_for_a_team_scoped_item_with_no_team_yet(db):
    """A student not yet placed on a cohort team still gets their
    assignment and progress row materialized for a team-scoped mission_run
    item — just no team progress row (and so no attempt) yet, rather than
    erroring the whole assignment."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author, team_policy="team")
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Team Mission, No Team Yet")
    db.add(lms_program)
    await db.flush()
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
        scope="team",
    )
    db.add(item)
    await db.flush()
    student = await _student(db)
    await db.commit()

    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    progress = (await db.execute(
        select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == assignment.id)
    )).scalars().one()
    assert progress.mission_attempt_id is None
    no_team_row = await db.scalar(
        select(LmsProgramTeamItemProgress).where(LmsProgramTeamItemProgress.item_id == item.id)
    )
    assert no_team_row is None


# ── team_mission_run_items (Phase 3, judge visibility) ──────────────────────

@pytest.mark.asyncio
async def test_team_mission_run_items_is_empty_for_a_team_with_no_team_scoped_mission_run(db):
    """The safety property that matters most: a cohort running only
    individual missions (every cohort today) must get back [] here, not
    an error and not a row for something that was never team-scoped."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author, team_policy="solo")
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Individual Only Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
        scope="individual",
    ))
    alice = await _student(db)
    await db.commit()
    team = await create_team(db, name="No Team Missions Team", created_by=alice.id, cohort_id=cohort.id)
    await db.commit()

    assert await team_mission_run_items(db, team_id=team.id) == []


@pytest.mark.asyncio
async def test_team_mission_run_items_groups_by_mission_and_reads_the_shared_attempt(db):
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author, team_policy="team")
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Team Mission With Steps")
    db.add(lms_program)
    await db.flush()
    # Two step items of the SAME run (mirrors how a design mission gets
    # split by mission_step_key) — must collapse to one entry, not two.
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
        scope="team", mission_step_key="components",
    ))
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
        scope="team", mission_step_key="conops",
    ))
    alice = await _student(db)
    bob = await _student(db)
    await db.commit()
    team = await create_team(db, name="Grouped Run Team", created_by=alice.id, cohort_id=cohort.id, member_ids=[bob.id])
    await db.commit()

    await assign_lms_program(db, user_id=alice.id, cohort_id=cohort.id)
    await assign_lms_program(db, user_id=bob.id, cohort_id=cohort.id)
    await db.commit()

    runs = await team_mission_run_items(db, team_id=team.id)
    assert len(runs) == 1
    assert runs[0]["mission_id"] == mission.id
    assert runs[0]["attempt_id"] is not None
    assert runs[0]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_team_mission_run_items_reports_not_started_before_any_assignment(db):
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author, team_policy="team")
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Team Mission Not Started")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
        scope="team",
    ))
    alice = await _student(db)
    await db.commit()
    team = await create_team(db, name="Not Assigned Yet Team", created_by=alice.id, cohort_id=cohort.id)
    await db.commit()

    runs = await team_mission_run_items(db, team_id=team.id)
    assert len(runs) == 1
    assert runs[0]["attempt_id"] is None
    assert runs[0]["status"] == "not_started"


@pytest.mark.asyncio
async def test_team_mission_run_items_finds_the_attempt_regardless_of_assignment_order(db):
    """The shared attempt lives on the one LmsProgramTeamItemProgress row
    for (item, team), so a teammate who registered *before* the team
    existed and got no attempt written to their own (unused) individual
    row can never hide the team's real, already-in-progress run — there's
    only one row to read, and it isn't theirs. (An earlier design
    duplicated the attempt id onto every teammate's own row instead and
    had to guess which one to trust — see git history if curious; this
    test just confirms the current single-source-of-truth design holds up
    under the same assignment-order scenario that broke it.)"""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author, team_policy="team")
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Mixed Assignment Order Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
        scope="team",
    ))
    alice = await _student(db)
    bob = await _student(db)
    await db.commit()

    # Alice registers/assigns BEFORE any team exists — no team progress
    # row gets created for her at all yet (the known Phase 2 gap).
    await assign_lms_program(db, user_id=alice.id, cohort_id=cohort.id)
    await db.commit()

    # The team forms afterward and Bob's own assignment DOES resolve a
    # real, shared attempt.
    team = await create_team(db, name="Mixed Order Team", created_by=alice.id, cohort_id=cohort.id)
    await join_team(db, team_id=team.id, user_id=bob.id)
    await db.commit()
    await assign_lms_program(db, user_id=bob.id, cohort_id=cohort.id)
    await db.commit()

    runs = await team_mission_run_items(db, team_id=team.id)
    assert len(runs) == 1
    assert runs[0]["attempt_id"] is not None
    assert runs[0]["status"] == "in_progress"


# ── guard_locked_submission_scope / validate_item_refs (Phase 3 hardening) ──

@pytest.mark.asyncio
async def test_guard_locked_submission_scope_blocks_a_mission_run_scope_change(db):
    """Regression: before this, only `submission` items had their scope
    locked after creation. A mission_run item's scope could be flipped
    individual->team (or back) after students already had attempts
    assigned, which would have `team_mission_run_items` read one
    teammate's *personal* attempt and report it as the team's shared run."""
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=uuid.uuid4(), position=1,
        item_type="mission_run", title="Some Run", scope="individual",
    )
    flip_to_team = LmsProgramItemIn(item_type="mission_run", title="Some Run", scope="team")
    with pytest.raises(HTTPException):
        guard_locked_submission_scope(item, flip_to_team)

    # Saving with the same scope (any other field edit) is still fine.
    no_op = LmsProgramItemIn(item_type="mission_run", title="Some Run", scope="individual")
    guard_locked_submission_scope(item, no_op)  # must not raise


@pytest.mark.asyncio
async def test_validate_item_refs_rejects_a_team_scoped_mission_run_against_a_solo_only_mission(db):
    """Regression: this used to only be caught deep inside
    assign_mission_run, at assign/sync time — by then it's too late to
    reject cleanly; the exception aborts sync_cohort_assignments' loop
    over every remaining student in the cohort. Catching it here, at
    authoring time, means the bad combination can never be saved."""
    author = await _author(db)
    solo_mission, solo_variant = await _mission_with_variant(db, author=author, team_policy="solo")
    team_mission, team_variant = await _mission_with_variant(db, author=author, team_policy="team")
    await db.commit()

    bad_body = LmsProgramItemIn(
        item_type="mission_run", title="Bad Team Run", scope="team",
        mission_id=solo_mission.id, variant_id=solo_variant.id,
    )
    with pytest.raises(HTTPException):
        await validate_item_refs(db, bad_body)

    good_body = LmsProgramItemIn(
        item_type="mission_run", title="Good Team Run", scope="team",
        mission_id=team_mission.id, variant_id=team_variant.id,
    )
    await validate_item_refs(db, good_body)  # must not raise

    # An individual-scoped item against the same solo mission is fine.
    individual_body = LmsProgramItemIn(
        item_type="mission_run", title="Solo Run", scope="individual",
        mission_id=solo_mission.id, variant_id=solo_variant.id,
    )
    await validate_item_refs(db, individual_body)  # must not raise


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
async def test_sync_creates_a_missing_assignment_for_a_team_member_with_none_yet(db):
    """The reported bug: a team advances into a cohort that had no
    checklist yet, so assign_lms_program no-ops and the student never
    gets an assignment at all — sync_cohort_assignments must create one
    outright once a checklist exists, not just backfill missing items on
    an assignment that's already there."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    student = await _student(db)
    await db.commit()

    # Team exists in the cohort (as advance_teams would leave behind),
    # but there's no checklist yet, so no assignment was ever created.
    await create_team(db, name="edos", created_by=student.id, cohort_id=cohort.id)
    await db.commit()
    assert await resolve_cohort_program(db, cohort.id) is None
    assert (await db.execute(
        select(LmsProgramAssignment).where(LmsProgramAssignment.cohort_id == cohort.id)
    )).scalars().first() is None

    # Ops sets up the phase's checklist after the fact.
    course = await _course(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Phase Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="course", title=course.title, course_id=course.id,
    ))
    await db.commit()

    # assign_lms_program materializes a fresh assignment's items itself, so
    # the newly-created assignment needs no further item backfill here —
    # `added` only counts items missing from an assignment that already existed.
    added = await sync_cohort_assignments(db, cohort_id=cohort.id)
    await db.commit()
    assert added == 0

    assignment = (await db.execute(
        select(LmsProgramAssignment).where(
            LmsProgramAssignment.cohort_id == cohort.id, LmsProgramAssignment.user_id == student.id,
        )
    )).scalars().first()
    assert assignment is not None
    progress_rows = (await db.execute(
        select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == assignment.id)
    )).scalars().all()
    assert len(progress_rows) == 1

    # Safe to call again — nothing missing now.
    assert await sync_cohort_assignments(db, cohort_id=cohort.id) == 0


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
async def test_gate_is_satisfied_once_a_required_team_scoped_mission_run_passes(db):
    """Regression: certificate_gate_satisfied used to check every required
    item's own individual progress row unconditionally, never resolving
    the shared team row a team-scoped item's real state lives on — a
    cohort with a required team-scoped item (mission_run or submission)
    could never satisfy the gate for anyone."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author, team_policy="team")
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Team Gated Checklist")
    db.add(lms_program)
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
        scope="team",
    ))
    alice = await _student(db)
    bob = await _student(db)
    await create_team(db, name="Gate Team", created_by=alice.id, cohort_id=cohort.id, member_ids=[bob.id])
    await db.commit()
    await assign_lms_program(db, user_id=alice.id, cohort_id=cohort.id)
    await assign_lms_program(db, user_id=bob.id, cohort_id=cohort.id)
    await db.commit()

    assert await certificate_gate_satisfied(db, cohort_id=cohort.id, user_id=alice.id) is False

    attempt = (await db.execute(select(MissionAttempt).where(MissionAttempt.mission_id == mission.id))).scalars().one()
    await decide_attempt(db, attempt=attempt, passed=True)
    await db.commit()

    # Satisfied for BOTH teammates, off the one shared attempt.
    assert await certificate_gate_satisfied(db, cohort_id=cohort.id, user_id=alice.id) is True
    assert await certificate_gate_satisfied(db, cohort_id=cohort.id, user_id=bob.id) is True


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
        item_type="pdf", title="Read this", optional=True,
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


# ── shared-attempt bugs (found live, 2026-09-14) ────────────────────────────

@pytest.mark.asyncio
async def test_sync_team_mission_runs_assigns_the_attempt_once_the_team_forms(db):
    """Regression: `_assign_team_mission_run` no-ops for a team-scoped
    mission_run item until the student is on a team, and nothing ever
    resynced it once one formed — the ordinary ops flow (register
    students, form teams afterward) left a team-scoped item permanently
    stuck at 'not started' for every team formed post-assignment."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author, team_policy="team")
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Late Team Checklist")
    db.add(lms_program)
    await db.flush()
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
        scope="team",
    )
    db.add(item)
    await db.flush()
    alice = await _student(db)
    bob = await _student(db)
    await db.commit()

    # Assigned BEFORE any team exists — same as `test_assign_lms_program_
    # skips_the_attempt_for_a_team_scoped_item_with_no_team_yet` above.
    await assign_lms_program(db, user_id=alice.id, cohort_id=cohort.id)
    await assign_lms_program(db, user_id=bob.id, cohort_id=cohort.id)
    await db.commit()
    assert await team_mission_run_items(db, team_id=uuid.uuid4()) == []  # no team yet, nothing to find

    team = await create_team(db, name="Formed Late", created_by=alice.id, cohort_id=cohort.id, member_ids=[bob.id])
    await db.commit()

    # Without the resync trigger, the team's own progress row would still
    # be missing/attempt-less here — `create_team` itself doesn't know
    # about LMS checklists.
    still_missing = await db.scalar(
        select(LmsProgramTeamItemProgress.mission_attempt_id).where(
            LmsProgramTeamItemProgress.item_id == item.id, LmsProgramTeamItemProgress.team_id == team.id,
        )
    )
    assert still_missing is None

    synced = await sync_team_mission_runs(db, team=team)
    await db.commit()
    assert synced == 1

    team_progress = (await db.execute(
        select(LmsProgramTeamItemProgress).where(
            LmsProgramTeamItemProgress.item_id == item.id, LmsProgramTeamItemProgress.team_id == team.id,
        )
    )).scalars().one()
    assert team_progress.mission_attempt_id is not None

    runs = await team_mission_run_items(db, team_id=team.id)
    assert len(runs) == 1
    assert runs[0]["attempt_id"] == team_progress.mission_attempt_id
    assert runs[0]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_sync_team_mission_runs_is_a_noop_for_a_cohortless_team(db):
    author = await _author(db)
    alice = await _student(db)
    team = await create_team(db, name="Self-formed", created_by=alice.id)  # no cohort_id
    await db.commit()
    assert await sync_team_mission_runs(db, team=team) == 0


@pytest.mark.asyncio
async def test_team_scoped_mission_split_into_steps_keeps_one_attempt_after_the_first_passes(db):
    """Regression: a mission split into several team-scoped checklist steps
    (mission_step_key) is supposed to share ONE attempt — but once the
    first step's attempt is no longer `in_progress` (passed here), syncing
    a later step used to mint a SECOND, disconnected attempt (its resume
    search only matches `in_progress`), and `team_mission_run_items` would
    then report whichever attempt happened to come first in position
    order — stale once it's the passed one, hiding the team's real,
    currently-active attempt from both the team and ops."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author, team_policy="team")
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Split Team Mission")
    db.add(lms_program)
    await db.flush()
    step_a = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title="Step A", mission_id=mission.id, variant_id=variant.id,
        scope="team", mission_step_key="components",
    )
    db.add(step_a)
    await db.flush()
    alice = await _student(db)
    bob = await _student(db)
    team = await create_team(db, name="Split Team", created_by=alice.id, cohort_id=cohort.id, member_ids=[bob.id])
    await db.commit()
    await assign_lms_program(db, user_id=alice.id, cohort_id=cohort.id)
    await assign_lms_program(db, user_id=bob.id, cohort_id=cohort.id)
    await db.commit()

    attempt = (await db.execute(select(MissionAttempt).where(MissionAttempt.mission_id == mission.id))).scalar_one()
    await decide_attempt(db, attempt=attempt, passed=True)
    await db.commit()

    # Ops adds a second step to the same mission run AFTER the first
    # attempt already passed, then syncs it onto both teammates.
    step_b = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="mission_run", title="Step B", mission_id=mission.id, variant_id=variant.id,
        scope="team", mission_step_key="conops",
    )
    db.add(step_b)
    await db.flush()
    alice_assignment = (await db.execute(
        select(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == alice.id, LmsProgramAssignment.cohort_id == cohort.id,
        )
    )).scalars().one()
    await sync_assignment_items(db, assignment=alice_assignment)
    await db.commit()

    # Still exactly one MissionAttempt for this mission — step B's sync
    # adopted step A's attempt instead of minting a second one.
    attempts = (await db.execute(
        select(MissionAttempt).where(MissionAttempt.mission_id == mission.id)
    )).scalars().all()
    assert len(attempts) == 1

    runs = await team_mission_run_items(db, team_id=team.id)
    assert len(runs) == 1
    assert runs[0]["attempt_id"] == attempt.id
    assert runs[0]["status"] == "passed"


@pytest.mark.asyncio
async def test_team_mission_run_items_finds_the_attempt_even_when_an_earlier_step_has_no_row_yet(db):
    """Regression: a split run's steps don't all necessarily get their
    LmsProgramTeamItemProgress row's mission_attempt_id populated at the
    same moment — step A's row can exist with mission_attempt_id still
    null while step B's already carries the real, shared attempt. Reading
    "first item that HAS a progress row" instead of "first item whose row
    actually carries an attempt id" used to report the run as not_started
    in that case, even though it had genuinely started."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author, team_policy="team")
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Partially Synced Split Mission")
    db.add(lms_program)
    await db.flush()
    step_a = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title="Step A", mission_id=mission.id, variant_id=variant.id,
        scope="team", mission_step_key="components",
    )
    step_b = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="mission_run", title="Step B", mission_id=mission.id, variant_id=variant.id,
        scope="team", mission_step_key="conops",
    )
    db.add_all([step_a, step_b])
    await db.flush()
    alice = await _student(db)
    team = await create_team(db, name="Partial Sync Team", created_by=alice.id, cohort_id=cohort.id)
    attempt = MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, team_id=team.id,
        attempt_no=1, status="in_progress", payload={},
    )
    db.add(attempt)
    await db.flush()
    # Step A's row exists (assigned) but hasn't picked up the attempt yet;
    # step B's already has it — same shared run, disagreeing rows.
    db.add(LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=step_a.id, team_id=team.id, status="pending", mission_attempt_id=None,
    ))
    db.add(LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=step_b.id, team_id=team.id, status="pending", mission_attempt_id=attempt.id,
    ))
    await db.commit()

    runs = await team_mission_run_items(db, team_id=team.id)
    assert len(runs) == 1
    assert runs[0]["attempt_id"] == attempt.id
    assert runs[0]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_individual_mission_split_into_steps_keeps_one_attempt_after_the_first_passes(db):
    """The individual-scope mirror of the team-side regression above:
    `sync_assignment_items` adding a second individual-scoped step for a
    mission whose original attempt already passed used to mint a second,
    disconnected attempt for that new step — leaving it pointing at a
    fresh, Design-less attempt instead of the one the student actually
    finished the mission on."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Split Solo Mission")
    db.add(lms_program)
    await db.flush()
    step_a = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title="Step A", mission_id=mission.id, variant_id=variant.id,
        mission_step_key="components",
    )
    db.add(step_a)
    await db.flush()
    student = await _student(db)
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    attempt = (await db.execute(
        select(MissionAttempt).where(MissionAttempt.user_id == student.id)
    )).scalar_one()
    await decide_attempt(db, attempt=attempt, passed=True)
    await db.commit()

    step_b = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="mission_run", title="Step B", mission_id=mission.id, variant_id=variant.id,
        mission_step_key="conops",
    )
    db.add(step_b)
    await db.flush()
    await sync_assignment_items(db, assignment=assignment)
    await db.commit()

    attempts = (await db.execute(
        select(MissionAttempt).where(MissionAttempt.user_id == student.id)
    )).scalars().all()
    assert len(attempts) == 1  # step B reused step A's attempt, not a fresh one

    step_b_progress = (await db.execute(
        select(LmsProgramItemProgress).where(
            LmsProgramItemProgress.assignment_id == assignment.id, LmsProgramItemProgress.item_id == step_b.id,
        )
    )).scalars().one()
    assert step_b_progress.mission_attempt_id == attempt.id


# ── team_setup authoring validation (2026-09-14) ────────────────────────────

def test_team_setup_must_be_team_scoped():
    body = LmsProgramItemIn(item_type="team_setup", title="Name your team", scope="individual")
    with pytest.raises(HTTPException) as exc_info:
        validate_item_payload(body)
    assert exc_info.value.status_code == 400
    assert "always team-scoped" in exc_info.value.detail


def test_team_setup_team_scoped_is_valid():
    body = LmsProgramItemIn(item_type="team_setup", title="Name your team", scope="team")
    validate_item_payload(body)  # does not raise


def test_team_setup_cannot_be_gated():
    body = LmsProgramItemIn(item_type="team_setup", title="Name your team", scope="team", gated=True)
    with pytest.raises(HTTPException) as exc_info:
        validate_item_payload(body)
    assert exc_info.value.status_code == 400
    assert "cannot be gated" in exc_info.value.detail


def test_team_setup_accepts_a_deadline():
    body = LmsProgramItemIn(
        item_type="team_setup", title="Name your team", scope="team",
        deadline_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    validate_item_payload(body)  # does not raise


def test_individual_items_and_quizzes_accept_a_deadline():
    quiz_body = LmsProgramItemIn(
        item_type="quiz", title="Knowledge Check",
        cohort_quiz_template_id=uuid.uuid4(),
        deadline_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    validate_item_payload(quiz_body)  # does not raise

    manual_body = LmsProgramItemIn(
        item_type="manual", title="Do a thing",
        deadline_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    validate_item_payload(manual_body)  # does not raise


# ── submission_multi_link authoring validation (2026-09-14) ────────────────

def test_submission_multi_link_is_valid_on_a_submission_item():
    body = LmsProgramItemIn(
        item_type="submission", title="Team deliverable", submission_prompt="links",
        submission_multi_link=True,
    )
    validate_item_payload(body)  # does not raise


def test_submission_multi_link_rejected_on_a_non_submission_item():
    body = LmsProgramItemIn(item_type="manual", title="Do a thing", submission_multi_link=True)
    with pytest.raises(HTTPException) as exc_info:
        validate_item_payload(body)
    assert exc_info.value.status_code == 400
    assert "multiple links" in exc_info.value.detail


# ── submission_link_labels authoring validation (2026-09-14) ───────────────

def test_submission_link_labels_is_valid_with_multi_link_on():
    body = LmsProgramItemIn(
        item_type="submission", title="Team deliverable", submission_prompt="links",
        submission_multi_link=True,
        submission_link_labels=[{"label": "Member 1 link", "required": True}, {"label": "Team link", "required": False}],
    )
    validate_item_payload(body)  # does not raise
    assert body.submission_link_labels[0].label == "Member 1 link"


def test_submission_link_labels_rejected_without_multi_link():
    body = LmsProgramItemIn(
        item_type="submission", title="Team deliverable", submission_prompt="links",
        submission_multi_link=False, submission_link_labels=[{"label": "Member 1 link", "required": True}],
    )
    with pytest.raises(HTTPException) as exc_info:
        validate_item_payload(body)
    assert exc_info.value.status_code == 400
    assert "submission_multi_link" in exc_info.value.detail


def test_submission_link_labels_rejects_empty_list():
    body = LmsProgramItemIn(
        item_type="submission", title="Team deliverable", submission_prompt="links",
        submission_multi_link=True, submission_link_labels=[],
    )
    with pytest.raises(HTTPException) as exc_info:
        validate_item_payload(body)
    assert exc_info.value.status_code == 400


def test_submission_link_labels_rejects_blank_label():
    body = LmsProgramItemIn(
        item_type="submission", title="Team deliverable", submission_prompt="links",
        submission_multi_link=True, submission_link_labels=[{"label": "   ", "required": True}],
    )
    with pytest.raises(HTTPException) as exc_info:
        validate_item_payload(body)
    assert exc_info.value.status_code == 400
    assert "blank" in exc_info.value.detail


def test_submission_link_labels_rejects_duplicate_labels():
    body = LmsProgramItemIn(
        item_type="submission", title="Team deliverable", submission_prompt="links",
        submission_multi_link=True,
        submission_link_labels=[{"label": "Team link", "required": True}, {"label": "Team link", "required": False}],
    )
    with pytest.raises(HTTPException) as exc_info:
        validate_item_payload(body)
    assert exc_info.value.status_code == 400
    assert "unique" in exc_info.value.detail


# ── submission_table_config authoring validation (2026-10-30) ──────────────

def test_submission_table_config_is_valid():
    body = LmsProgramItemIn(
        item_type="submission", title="Tabular Grid",
        submission_table_config={
            "tag_label": "Category",
            "tags": ["Tag A", "Tag B"],
            "allow_custom_tags": True,
            "columns": [
                {"key": "url", "label": "Link", "type": "link", "required": False},
                {"key": "score", "label": "Score", "type": "text", "required": False},
                {"key": "status", "label": "Status", "type": "select", "options": ["Active", "Archived"], "required": False},
            ],
        },
    )
    validate_item_payload(body)
    assert body.submission_table_config.tag_label == "Category"
    assert len(body.submission_table_config.columns) == 3


def test_submission_table_config_rejects_non_submission():
    body = LmsProgramItemIn(
        item_type="manual", title="Manual Step",
        submission_table_config={"tag_label": "Tag", "columns": []},
    )
    with pytest.raises(HTTPException) as exc_info:
        validate_item_payload(body)
    assert exc_info.value.status_code == 400
    assert "submission" in exc_info.value.detail


def test_submission_table_config_rejects_duplicate_column_keys():
    body = LmsProgramItemIn(
        item_type="submission", title="Tabular Grid",
        submission_table_config={
            "tag_label": "Tag",
            "columns": [
                {"key": "url", "label": "Link 1", "type": "link"},
                {"key": "url", "label": "Link 2", "type": "link"},
            ],
        },
    )
    with pytest.raises(HTTPException) as exc_info:
        validate_item_payload(body)
    assert exc_info.value.status_code == 400
    assert "unique" in exc_info.value.detail


@pytest.mark.asyncio
async def test_resync_wires_a_team_mission_run_added_after_the_team_was_assigned(db):
    """Regression (found live, 2026-09-19 — team Orbit3): ops added six
    team-scoped `mission_run` steps to a cohort override whose teams were
    already formed and assigned. Every member got their individual
    placeholder row for each new item, but no team ever got its
    `LmsProgramTeamItemProgress` row or the shared `MissionAttempt`, so
    the checklist tile had no `mission_attempt_id` and clicking "Open"
    silently did nothing.

    The cause was `sync_assignment_items` gating the team-side wiring on
    the same `missing` check as the individual placeholder: the moment a
    student holds their placeholder, the item stops being "missing" and
    `_assign_team_mission_run` is never reached. "Resync students"
    therefore reported 0 items added forever and could never repair it.

    This reproduces that exact state — placeholder present, team row
    absent — and asserts a resync now fixes it."""
    author = await _author(db)
    program, cohort = await _program_and_cohort(db)
    mission, variant = await _mission_with_variant(db, author=author, team_policy="team")
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Late Team Mission Program")
    db.add(lms_program)
    await db.flush()
    # Something already on the checklist, so the cohort resolves and the
    # students get a real assignment before the team item is ever added.
    seed = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="manual", title="Kickoff",
    )
    db.add(seed)
    await db.flush()

    alice, bob = await _student(db), await _student(db)
    team = await create_team(db, name="Orbit3", created_by=alice.id, cohort_id=cohort.id)
    await join_team(db, team_id=team.id, user_id=bob.id)
    for student in (alice, bob):
        await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()

    # Ops adds the team-scoped mission_run step AFTER everyone's assigned.
    late_item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="mission_run", title="Team's mission components", mission_id=mission.id,
        variant_id=variant.id, scope="team", mission_step_key="components",
    )
    db.add(late_item)
    await db.flush()

    # Reproduce the live state precisely: the individual placeholder rows
    # exist (so `missing` is empty for this item) while the team row does
    # not. This is what one earlier resync would have left behind.
    for student in (alice, bob):
        assignment = (await db.execute(
            select(LmsProgramAssignment).where(
                LmsProgramAssignment.user_id == student.id, LmsProgramAssignment.cohort_id == cohort.id,
            )
        )).scalars().one()
        db.add(LmsProgramItemProgress(
            id=uuid.uuid4(), assignment_id=assignment.id, item_id=late_item.id,
        ))
    await db.commit()

    team_row = await db.scalar(
        select(LmsProgramTeamItemProgress).where(
            LmsProgramTeamItemProgress.item_id == late_item.id, LmsProgramTeamItemProgress.team_id == team.id,
        )
    )
    assert team_row is None  # the broken state, as observed in production

    # The "Resync students" path. Before the fix this returned 0 and
    # changed nothing, no matter how many times it was called.
    added = await sync_cohort_assignments(db, cohort_id=cohort.id)
    await db.commit()
    assert added == 1

    team_row = await db.scalar(
        select(LmsProgramTeamItemProgress).where(
            LmsProgramTeamItemProgress.item_id == late_item.id, LmsProgramTeamItemProgress.team_id == team.id,
        )
    )
    assert team_row is not None
    assert team_row.mission_attempt_id is not None

    # Exactly one attempt for the whole team — not one per member.
    attempts = (await db.execute(
        select(MissionAttempt).where(MissionAttempt.mission_id == mission.id)
    )).scalars().all()
    assert len(attempts) == 1
    assert attempts[0].team_id == team.id
    assert team_row.mission_attempt_id == attempts[0].id

    # The tile can now resolve an attempt to open.
    runs = await team_mission_run_items(db, team_id=team.id)
    assert len(runs) == 1
    assert runs[0]["attempt_id"] == attempts[0].id


    # And a second resync is a genuine no-op, not a second attempt.
    assert await sync_cohort_assignments(db, cohort_id=cohort.id) == 0
    await db.commit()
    attempts = (await db.execute(
        select(MissionAttempt).where(MissionAttempt.mission_id == mission.id)
    )).scalars().all()
    assert len(attempts) == 1


def test_team_setup_never_gates_subsequent_items():
    from app.services.lms.program import compute_lock_states
    from unittest.mock import MagicMock

    item_team_setup = MagicMock(id=uuid.uuid4(), position=1, item_type="team_setup", optional=False, gated=False)
    item_task_1 = MagicMock(id=uuid.uuid4(), position=2, item_type="manual", optional=False, gated=True)
    item_task_2 = MagicMock(id=uuid.uuid4(), position=3, item_type="manual", optional=False, gated=True)

    # team_setup is NOT done, but it should not block item_task_1 even though item_task_1 is gated
    statuses = {
        item_team_setup.id: "pending",
        item_task_1.id: "done",
        item_task_2.id: "pending",
    }
    items = [item_team_setup, item_task_1, item_task_2]
    locks = compute_lock_states(items, statuses)

    # item_team_setup is never locked
    assert locks[item_team_setup.id] is False
    # item_task_1 was gated, but team_setup is excluded from blocking, so item_task_1 is unlocked!
    assert locks[item_task_1.id] is False
    # item_task_2 is gated, item_task_1 is done, team_setup is pending (ignored) -> unlocked!
    assert locks[item_task_2.id] is False
