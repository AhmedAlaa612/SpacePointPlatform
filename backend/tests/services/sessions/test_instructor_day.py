"""The instructor daily loop (operations doc §4-§12, built 2026-08-24).

The behaviours worth pinning down:
  * checklist resolution is override-not-merge across program/cohort/session;
  * a day can't be submitted with a required item unticked or a proof-required
    item unproven, and says everything outstanding at once;
  * return -> fix -> resubmit -> approve round-trips, and an approved day is
    locked against further instructor edits;
  * `maybe_complete_cohort` fires only when every session is completed AND
    every day is approved AND somebody was actually staffed — the last guard
    being the one that stops an unstaffed cohort completing itself.
"""

import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.sessions.checklist import DeliveryChecklistItem, InstructorSessionDay
from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.sessions.session_report import SessionReport
from app.models.user import User
from app.services.sessions import day as svc


async def _make(db, *, session_count: int = 2):
    program = Program(
        id=uuid.uuid4(), code=f"DAY-{uuid.uuid4().hex[:8]}", name="Day Loop Program",
        program_type="workshop", pricing_model="free", active=True,
        completion_rule_type="percentage", completion_rule_value=70,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Day Loop Cohort",
        status="running", visibility="public",
    )
    db.add(cohort)
    await db.flush()
    sessions = []
    for i in range(session_count):
        s = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 1 + i))
        db.add(s)
        sessions.append(s)
    await db.flush()
    return program, cohort, sessions


async def _instructor(db, name="Muna A") -> User:
    user = User(
        id=uuid.uuid4(), full_name=name, email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=["instructor"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _assign(db, session, user):
    role_id = await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == "Lead Facilitator"))
    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=session.id, user_id=user.id, role_id=role_id,
    ))
    await db.flush()


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ops Person", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _proof(db, session, user) -> SessionReport:
    report = SessionReport(
        id=uuid.uuid4(), cohort_id=session.cohort_id, session_id=session.id,
        uploaded_by=user.id, file_ref=f"{uuid.uuid4().hex}_photo.jpg",
    )
    db.add(report)
    await db.flush()
    return report


# ── checklist resolution: override, not merge ───────────────────────────────

@pytest.mark.asyncio
async def test_checklist_resolves_program_then_cohort_then_session(db):
    program, cohort, sessions = await _make(db)
    session = sessions[0]

    db.add(DeliveryChecklistItem(id=uuid.uuid4(), program_id=program.id, title="Program item"))
    await db.flush()
    assert [i.title for i in await svc.resolve_checklist(db, session)] == ["Program item"]

    db.add(DeliveryChecklistItem(id=uuid.uuid4(), cohort_id=cohort.id, title="Cohort item"))
    await db.flush()
    assert [i.title for i in await svc.resolve_checklist(db, session)] == ["Cohort item"], \
        "the cohort overrides the program outright — it does not merge"

    db.add(DeliveryChecklistItem(id=uuid.uuid4(), session_id=session.id, title="Session item"))
    await db.flush()
    assert [i.title for i in await svc.resolve_checklist(db, session)] == ["Session item"]


@pytest.mark.asyncio
async def test_clearing_a_level_falls_back_to_the_one_above(db):
    """Saving an empty list is how ops goes back to inheriting."""
    program, cohort, sessions = await _make(db)
    ops = await _ops(db)
    await svc.set_checklist_items(
        db, lines=[{"title": "Program item"}], actor_user_id=ops.id, program_id=program.id
    )
    await svc.set_checklist_items(
        db, lines=[{"title": "Cohort item"}], actor_user_id=ops.id, cohort_id=cohort.id
    )
    assert [i.title for i in await svc.resolve_checklist(db, sessions[0])] == ["Cohort item"]

    await svc.set_checklist_items(db, lines=[], actor_user_id=ops.id, cohort_id=cohort.id)
    assert [i.title for i in await svc.resolve_checklist(db, sessions[0])] == ["Program item"]


async def _role(db, name: str) -> uuid.UUID:
    return await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))


@pytest.mark.asyncio
async def test_role_checklist_replaces_general_not_adds_to_it(db):
    """A role with its own items at a level sees *only* those — the general
    ones at that same level don't also apply."""
    _program, cohort, sessions = await _make(db)
    session = sessions[0]
    lead_id, facilitator_id = await _role(db, "Lead Facilitator"), await _role(db, "Facilitator")

    db.add(DeliveryChecklistItem(id=uuid.uuid4(), cohort_id=cohort.id, title="General item"))
    db.add(DeliveryChecklistItem(id=uuid.uuid4(), cohort_id=cohort.id, role_id=lead_id, title="Lead-only item"))
    await db.flush()

    lead_items = await svc.resolve_checklist(db, session, lead_id)
    assert [i.title for i in lead_items] == ["Lead-only item"], \
        "Lead has their own list at this level — the general item must not also appear"

    facilitator_items = await svc.resolve_checklist(db, session, facilitator_id)
    assert [i.title for i in facilitator_items] == ["General item"], \
        "Facilitator has nothing role-specific at this level, so falls back to general"

    no_role_items = await svc.resolve_checklist(db, session, None)
    assert [i.title for i in no_role_items] == ["General item"]


@pytest.mark.asyncio
async def test_role_fallback_is_per_level_not_across_levels(db):
    """A role checklist set at the program level must not leak past a cohort
    that has its own (general-only) items — level still wins outright first,
    role fallback only applies within whichever level wins."""
    program, cohort, sessions = await _make(db)
    session = sessions[0]
    lead_id = await _role(db, "Lead Facilitator")

    db.add(DeliveryChecklistItem(id=uuid.uuid4(), program_id=program.id, role_id=lead_id, title="Program Lead item"))
    db.add(DeliveryChecklistItem(id=uuid.uuid4(), cohort_id=cohort.id, title="Cohort general item"))
    await db.flush()

    items = await svc.resolve_checklist(db, session, lead_id)
    assert [i.title for i in items] == ["Cohort general item"], \
        "the cohort level has something (general), so it wins outright over the program's Lead-specific list"


@pytest.mark.asyncio
async def test_setting_a_role_bucket_does_not_touch_the_general_one(db):
    program, _cohort, sessions = await _make(db)
    ops = await _ops(db)
    lead_id = await _role(db, "Lead Facilitator")

    await svc.set_checklist_items(db, lines=[{"title": "General"}], actor_user_id=ops.id, program_id=program.id)
    await svc.set_checklist_items(
        db, lines=[{"title": "Lead only"}], actor_user_id=ops.id, program_id=program.id, role_id=lead_id,
    )

    general = await svc.list_checklist_items(db, program_id=program.id)
    lead = await svc.list_checklist_items(db, program_id=program.id, role_id=lead_id)
    assert [i.title for i in general] == ["General"]
    assert [i.title for i in lead] == ["Lead only"]

    # Clearing the Lead bucket falls back to general for Lead; general itself
    # is untouched.
    await svc.set_checklist_items(db, lines=[], actor_user_id=ops.id, program_id=program.id, role_id=lead_id)
    items = await svc.resolve_checklist(db, sessions[0], lead_id)
    assert [i.title for i in items] == ["General"]


@pytest.mark.asyncio
async def test_checklist_must_belong_to_exactly_one_level(db):
    program, cohort, _sessions = await _make(db)
    ops = await _ops(db)
    with pytest.raises(HTTPException) as exc:
        await svc.set_checklist_items(
            db, lines=[{"title": "x"}], actor_user_id=ops.id,
            program_id=program.id, cohort_id=cohort.id,
        )
    assert exc.value.status_code == 400


# ── check-in ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_in_records_arrival_and_is_idempotent(db):
    _p, _c, sessions = await _make(db)
    user = await _instructor(db)
    await _assign(db, sessions[0], user)

    day = await svc.check_in(db, sessions[0].id, user, att_status="present")
    first = day.checked_in_at
    assert first is not None
    day = await svc.check_in(db, sessions[0].id, user, att_status="present")
    assert day.checked_in_at == first, "tapping twice must not move the recorded arrival time"


@pytest.mark.asyncio
async def test_declaring_absence_records_the_reason_and_clears_arrival(db):
    _p, _c, sessions = await _make(db)
    user = await _instructor(db)
    await _assign(db, sessions[0], user)

    await svc.check_in(db, sessions[0].id, user, att_status="present")
    day = await svc.check_in(db, sessions[0].id, user, att_status="absent", reason="driving test")
    assert day.att_status == "absent"
    assert day.absence_reason == "driving test"
    assert day.checked_in_at is None


@pytest.mark.asyncio
async def test_an_unassigned_instructor_gets_404_not_403(db):
    """Don't leak which sessions exist — same convention as delivery.py."""
    _p, _c, sessions = await _make(db)
    stranger = await _instructor(db, "Not Assigned")
    with pytest.raises(HTTPException) as exc:
        await svc.check_in(db, sessions[0].id, stranger, att_status="present")
    assert exc.value.status_code == 404


# ── submission gates ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cannot_submit_before_checking_in(db):
    _p, _c, sessions = await _make(db)
    user = await _instructor(db)
    await _assign(db, sessions[0], user)
    with pytest.raises(HTTPException) as exc:
        await svc.submit_day(db, sessions[0].id, user)
    assert exc.value.status_code == 409
    assert "Check in" in exc.value.detail


@pytest.mark.asyncio
async def test_submission_lists_every_outstanding_requirement_at_once(db):
    _p, cohort, sessions = await _make(db)
    user = await _instructor(db)
    ops = await _ops(db)
    await _assign(db, sessions[0], user)
    await svc.set_checklist_items(
        db, actor_user_id=ops.id, cohort_id=cohort.id,
        lines=[
            {"title": "Kits distributed", "is_required": True},
            {"title": "Setup photo", "is_required": True, "requires_proof": True},
        ],
    )
    await svc.check_in(db, sessions[0].id, user, att_status="present")

    with pytest.raises(HTTPException) as exc:
        await svc.submit_day(db, sessions[0].id, user)
    detail = exc.value.detail
    assert "Kits distributed" in detail and "Setup photo" in detail, \
        "an instructor should see everything outstanding in one go"


@pytest.mark.asyncio
async def test_a_ticked_but_unproven_item_still_blocks_submission(db):
    _p, cohort, sessions = await _make(db)
    user = await _instructor(db)
    ops = await _ops(db)
    await _assign(db, sessions[0], user)
    items = await svc.set_checklist_items(
        db, actor_user_id=ops.id, cohort_id=cohort.id,
        lines=[{"title": "Setup photo", "is_required": True, "requires_proof": True}],
    )
    await svc.check_in(db, sessions[0].id, user, att_status="present")
    await svc.set_checklist_progress(
        db, sessions[0].id, user, checklist_item_id=items[0].id, is_done=True
    )
    with pytest.raises(HTTPException) as exc:
        await svc.submit_day(db, sessions[0].id, user)
    assert "needs a photo" in exc.value.detail

    report = await _proof(db, sessions[0], user)
    await svc.set_checklist_progress(
        db, sessions[0].id, user, checklist_item_id=items[0].id, proof_report_id=report.id
    )
    day = await svc.submit_day(db, sessions[0].id, user)
    assert day.status == "submitted"


@pytest.mark.asyncio
async def test_an_assigned_instructors_role_is_picked_up_automatically(db):
    """End to end: nobody passes role_id explicitly on the instructor-facing
    calls — it's resolved from their own `SessionInstructor` assignment."""
    _p, cohort, sessions = await _make(db)
    lead = await _instructor(db, "Lead Mona")
    facilitator = await _instructor(db, "Facilitator Yousef")
    ops = await _ops(db)
    await _assign(db, sessions[0], lead)  # _assign staffs as Lead Facilitator
    facilitator_id = await _role(db, "Facilitator")
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=sessions[0].id, user_id=facilitator.id, role_id=facilitator_id))
    await db.flush()

    lead_id = await _role(db, "Lead Facilitator")
    await svc.set_checklist_items(
        db, actor_user_id=ops.id, cohort_id=cohort.id, role_id=lead_id,
        lines=[{"title": "Lead-only setup check"}],
    )
    await svc.set_checklist_items(
        db, actor_user_id=ops.id, cohort_id=cohort.id,
        lines=[{"title": "General setup check"}],
    )

    lead_detail = await svc.get_day_detail(db, sessions[0].id, lead)
    assert [i["title"] for i in lead_detail["checklist"]] == ["Lead-only setup check"]

    facilitator_detail = await svc.get_day_detail(db, sessions[0].id, facilitator)
    assert [i["title"] for i in facilitator_detail["checklist"]] == ["General setup check"]


@pytest.mark.asyncio
async def test_an_absence_needs_nothing_else_to_submit(db):
    _p, cohort, sessions = await _make(db)
    user = await _instructor(db)
    ops = await _ops(db)
    await _assign(db, sessions[0], user)
    await svc.set_checklist_items(
        db, actor_user_id=ops.id, cohort_id=cohort.id,
        lines=[{"title": "Kits distributed", "is_required": True}],
    )
    await svc.check_in(db, sessions[0].id, user, att_status="absent", reason="exam")
    day = await svc.submit_day(db, sessions[0].id, user)
    assert day.status == "submitted"


# ── review round trip ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_return_then_resubmit_then_approve(db):
    _p, _c, sessions = await _make(db)
    user = await _instructor(db)
    ops = await _ops(db)
    await _assign(db, sessions[0], user)

    await svc.check_in(db, sessions[0].id, user, att_status="present")
    day = await svc.submit_day(db, sessions[0].id, user)

    returned = await svc.return_day(db, day.id, ops.id, comment="Checklist item 6 needs evidence")
    assert returned.status == "changes_required"
    assert returned.review_comment == "Checklist item 6 needs evidence"

    resubmitted = await svc.submit_day(db, sessions[0].id, user)
    assert resubmitted.status == "submitted"
    assert resubmitted.review_comment is None, \
        "a resubmitted day must not still look rejected"

    approved = await svc.approve_day(db, day.id, ops.id)
    assert approved.status == "approved"


@pytest.mark.asyncio
async def test_returning_without_a_comment_is_refused(db):
    _p, _c, sessions = await _make(db)
    user = await _instructor(db)
    ops = await _ops(db)
    await _assign(db, sessions[0], user)
    await svc.check_in(db, sessions[0].id, user, att_status="present")
    day = await svc.submit_day(db, sessions[0].id, user)

    with pytest.raises(HTTPException) as exc:
        await svc.return_day(db, day.id, ops.id, comment="   ")
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_an_approved_day_is_locked_against_instructor_edits(db):
    _p, _c, sessions = await _make(db)
    user = await _instructor(db)
    ops = await _ops(db)
    await _assign(db, sessions[0], user)
    await svc.check_in(db, sessions[0].id, user, att_status="present")
    day = await svc.submit_day(db, sessions[0].id, user)
    await svc.approve_day(db, day.id, ops.id)

    with pytest.raises(HTTPException) as exc:
        await svc.check_in(db, sessions[0].id, user, att_status="absent", reason="changed my mind")
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_approving_an_unsubmitted_day_is_refused(db):
    _p, _c, sessions = await _make(db)
    user = await _instructor(db)
    ops = await _ops(db)
    await _assign(db, sessions[0], user)
    await svc.check_in(db, sessions[0].id, user, att_status="present")
    day = (await db.execute(select(InstructorSessionDay))).scalars().first()

    with pytest.raises(HTTPException) as exc:
        await svc.approve_day(db, day.id, ops.id)
    assert exc.value.status_code == 409


# ── cohort auto-completion ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cohort_completes_only_when_every_day_is_approved(db):
    _p, cohort, sessions = await _make(db, session_count=2)
    user = await _instructor(db)
    ops = await _ops(db)
    for s in sessions:
        await _assign(db, s, user)
        s.completed_at = datetime.now(timezone.utc)
    await db.flush()

    days = []
    for s in sessions:
        await svc.check_in(db, s.id, user, att_status="present")
        days.append(await svc.submit_day(db, s.id, user))

    await svc.approve_day(db, days[0].id, ops.id)
    assert await svc.maybe_complete_cohort(db, cohort.id, ops.id) is False, \
        "one day still unapproved — the cohort must not complete"

    await svc.approve_day(db, days[1].id, ops.id)
    assert await svc.maybe_complete_cohort(db, cohort.id, ops.id) is True
    await db.refresh(cohort)
    assert cohort.status == "completed"


@pytest.mark.asyncio
async def test_an_unstaffed_cohort_never_completes_itself(db):
    """Zero day rows makes "all approved" vacuously true — the staffing guard
    is what stops a cohort nobody taught from completing the moment its last
    session is marked done."""
    _p, cohort, sessions = await _make(db)
    ops = await _ops(db)
    for s in sessions:
        s.completed_at = datetime.now(timezone.utc)
    await db.flush()

    assert await svc.cohort_is_fully_reviewed(db, cohort.id) is False
    assert await svc.maybe_complete_cohort(db, cohort.id, ops.id) is False
    await db.refresh(cohort)
    assert cohort.status != "completed"


@pytest.mark.asyncio
async def test_an_undelivered_session_blocks_completion(db):
    _p, cohort, sessions = await _make(db, session_count=2)
    user = await _instructor(db)
    ops = await _ops(db)
    for s in sessions:
        await _assign(db, s, user)
    # Only the first session actually got delivered.
    sessions[0].completed_at = datetime.now(timezone.utc)
    await db.flush()

    await svc.check_in(db, sessions[0].id, user, att_status="present")
    day = await svc.submit_day(db, sessions[0].id, user)
    await svc.approve_day(db, day.id, ops.id)

    assert await svc.cohort_is_fully_reviewed(db, cohort.id) is False


@pytest.mark.asyncio
async def test_an_approved_absence_still_counts_as_reviewed(db):
    """An acknowledged absence is a reviewed day — it just isn't a paid one."""
    _p, cohort, sessions = await _make(db, session_count=1)
    user = await _instructor(db)
    ops = await _ops(db)
    await _assign(db, sessions[0], user)
    sessions[0].completed_at = datetime.now(timezone.utc)
    await db.flush()

    await svc.check_in(db, sessions[0].id, user, att_status="absent", reason="exam")
    day = await svc.submit_day(db, sessions[0].id, user)
    await svc.approve_day(db, day.id, ops.id)

    assert await svc.cohort_is_fully_reviewed(db, cohort.id) is True


# ── the ops session board ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_session_board_buckets_by_lifecycle(db):
    _p, _cohort, sessions = await _make(db, session_count=3)
    running, upcoming, done = sessions
    running.started_at = datetime.now(timezone.utc)
    done.started_at = datetime.now(timezone.utc)
    done.completed_at = datetime.now(timezone.utc)
    await db.flush()

    board = await svc.session_board(db)

    assert {r["session_id"] for r in board["running"]} == {running.id}
    assert {r["session_id"] for r in board["upcoming"]} == {upcoming.id}
    assert {r["session_id"] for r in board["done"]} == {done.id}
    assert board["done_total"] == 1


@pytest.mark.asyncio
async def test_session_board_done_is_paginated(db):
    _p, _cohort, sessions = await _make(db, session_count=7)
    for s in sessions:
        s.started_at = datetime.now(timezone.utc)
        s.completed_at = datetime.now(timezone.utc)
    await db.flush()

    page1 = await svc.session_board(db, done_offset=0, done_limit=5)
    assert len(page1["done"]) == 5
    assert page1["done_total"] == 7

    page2 = await svc.session_board(db, done_offset=5, done_limit=5)
    assert len(page2["done"]) == 2
    assert page2["done_total"] == 7

    seen = {r["session_id"] for r in page1["done"]} | {r["session_id"] for r in page2["done"]}
    assert seen == {s.id for s in sessions}, "no overlap and nothing missing across pages"
