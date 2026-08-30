"""Cohort-level staffing (2026-08-24).

Covers the three things this layer actually adds on top of the session-scoped
marketplace, since everything else delegates to `staffing.py` and is already
tested there:

  1. one role per instructor per cohort — the operator's rule, enforced here
     against both assignment rows and live SessionInstructor rows;
  2. registering once against a cohort call fans out to per-session interest
     rows (and reconciles them when the ticked days change);
  3. selection assigns exactly the ticked days and snapshots the rate that was
     on offer, so a later rate edit can't reprice an agreed assignment.

File named `test_cohort_staffing.py` — basenames must be unique across the
whole suite (no `__init__.py` in tests/), and `test_staffing.py` already
exists in this directory.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_assignment import CohortInstructorAssignment
from app.models.sessions.cohort_call_interest import CohortCallInterest
from app.models.sessions.cohort_opening import CohortOpening
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.sessions import cohort_staffing, staffing


async def _role_id(db, name: str = "Lead Facilitator"):
    return await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))


async def _make_cohort(db, *, session_count: int = 3) -> tuple[Cohort, list[Session]]:
    program = Program(
        id=uuid.uuid4(), code=f"COH-{uuid.uuid4().hex[:8]}", name="Cohort Staffing Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="TDRA Test Camp",
        status="planned", visibility="public",
        starts_on=date(2026, 10, 10), ends_on=date(2026, 10, 10 + session_count - 1),
    )
    db.add(cohort)
    await db.flush()
    sessions = []
    for i in range(session_count):
        s = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 10, 10 + i))
        db.add(s)
        sessions.append(s)
    await db.flush()
    return cohort, sessions


async def _make_instructor(db, name: str = "Muna A") -> User:
    user = User(
        id=uuid.uuid4(), full_name=name, email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=["instructor"],
    )
    db.add(user)
    await db.flush()
    return user


async def _offer_role(db, cohort, role_id, *, slots: int = 3, amount=None):
    """`register_interest` refuses a role the session isn't soliciting for —
    correct behaviour, so tests that apply for a named role have to configure
    the offer first, exactly as ops would."""
    db.add(CohortOpening(
        id=uuid.uuid4(), cohort_id=cohort.id, role_id=role_id, slots=slots, amount_aed=amount,
    ))
    await db.flush()


async def _open_cohort_call(db, cohort, sessions, actor=None):
    call, _ok, _failed = await staffing.open_cohort_call(
        db, cohort.id, session_ids=[s.id for s in sessions],
        actor_user_id=actor.id if actor else None,
    )
    await db.flush()
    return call


# ── one role per cohort ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_second_role_in_same_cohort_is_refused(db):
    cohort, sessions = await _make_cohort(db)
    user = await _make_instructor(db)
    lead, assistant = await _role_id(db, "Lead Facilitator"), await _role_id(db, "Assistant Facilitator")

    await cohort_staffing.select_for_cohort(
        db, cohort_id=cohort.id, user_ids=[user.id], role_id=lead,
        session_ids=[sessions[0].id],
    )
    with pytest.raises(HTTPException) as exc:
        await cohort_staffing.select_for_cohort(
            db, cohort_id=cohort.id, user_ids=[user.id], role_id=assistant,
            session_ids=[sessions[1].id],
        )
    assert exc.value.status_code == 409
    # The message has to name the clash — ops needs to know what they already are.
    assert "Lead Facilitator" in exc.value.detail


@pytest.mark.asyncio
async def test_same_role_again_is_fine_and_adds_sessions(db):
    """Re-picking somebody for more days of the same cohort is the normal way
    an assignment grows, not a clash."""
    cohort, sessions = await _make_cohort(db)
    user = await _make_instructor(db)
    lead = await _role_id(db)

    await cohort_staffing.select_for_cohort(
        db, cohort_id=cohort.id, user_ids=[user.id], role_id=lead, session_ids=[sessions[0].id],
    )
    await cohort_staffing.select_for_cohort(
        db, cohort_id=cohort.id, user_ids=[user.id], role_id=lead, session_ids=[sessions[1].id],
    )
    assigned = (await db.execute(
        select(SessionInstructor).join(Session, Session.id == SessionInstructor.session_id)
        .where(Session.cohort_id == cohort.id, SessionInstructor.user_id == user.id)
    )).scalars().all()
    assert len(assigned) == 2
    rows = (await db.execute(
        select(CohortInstructorAssignment).where(
            CohortInstructorAssignment.cohort_id == cohort.id,
            CohortInstructorAssignment.user_id == user.id,
        )
    )).scalars().all()
    assert len(rows) == 1, "one assignment row per (cohort, user, role), not one per session"


@pytest.mark.asyncio
async def test_role_clash_is_caught_against_direct_assign_rows_too(db):
    """Somebody put on a session through the pre-existing direct-assign path
    has no assignment row — the rule still has to see them."""
    cohort, sessions = await _make_cohort(db)
    user = await _make_instructor(db)
    lead, assistant = await _role_id(db, "Lead Facilitator"), await _role_id(db, "Assistant Facilitator")

    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=sessions[0].id, user_id=user.id, role_id=lead,
    ))
    await db.flush()

    with pytest.raises(HTTPException) as exc:
        await cohort_staffing.select_for_cohort(
            db, cohort_id=cohort.id, user_ids=[user.id], role_id=assistant,
            session_ids=[sessions[1].id],
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_different_roles_in_different_cohorts_are_allowed(db):
    """The operator's example: Assistant in Cohort A, Instructor in Cohort B."""
    cohort_a, sessions_a = await _make_cohort(db, session_count=1)
    cohort_b, sessions_b = await _make_cohort(db, session_count=1)
    user = await _make_instructor(db)
    lead, assistant = await _role_id(db, "Lead Facilitator"), await _role_id(db, "Assistant Facilitator")

    await cohort_staffing.select_for_cohort(
        db, cohort_id=cohort_a.id, user_ids=[user.id], role_id=assistant,
        session_ids=[sessions_a[0].id],
    )
    await cohort_staffing.select_for_cohort(
        db, cohort_id=cohort_b.id, user_ids=[user.id], role_id=lead,
        session_ids=[sessions_b[0].id],
    )
    rows = (await db.execute(
        select(CohortInstructorAssignment).where(CohortInstructorAssignment.user_id == user.id)
    )).scalars().all()
    assert {r.cohort_id for r in rows} == {cohort_a.id, cohort_b.id}


# ── interest fans out to per-session rows ───────────────────────────────────

@pytest.mark.asyncio
async def test_registering_once_writes_per_session_interest_for_ticked_days(db):
    cohort, sessions = await _make_cohort(db)
    user = await _make_instructor(db)
    call = await _open_cohort_call(db, cohort, sessions)

    await cohort_staffing.register_cohort_interest(
        db, cohort_id=cohort.id, cohort_call_id=call.id, user=user,
        session_ids=[sessions[0].id, sessions[2].id],
        note="I'd like this one", needs_transport=True, travelling_from_other_city=True,
        concerns="Need an early ride",
    )
    per_session_rows = (await db.execute(
        select(InstructorInterest).where(InstructorInterest.user_id == user.id)
    )).scalars().all()
    assert {r.session_id for r in per_session_rows} == {sessions[0].id, sessions[2].id}
    # The session-scoped Staffing tab reads support answers off these rows,
    # not the cohort-level one — they must carry the same answers
    # (2026-08-30 fix: register_cohort_interest used to drop them here).
    for r in per_session_rows:
        assert r.needs_transport is True
        assert r.travelling_from_other_city is True
        assert r.concerns == "Need an early ride"

    cohort_row = (await db.execute(
        select(CohortCallInterest).where(CohortCallInterest.cohort_call_id == call.id)
    )).scalars().one()
    assert cohort_row.needs_transport is True
    assert cohort_row.travelling_from_other_city is True
    assert cohort_row.note == "I'd like this one"


@pytest.mark.asyncio
async def test_changing_ticked_days_reconciles_instead_of_duplicating(db):
    """Changing which days you can do is routine — the per-session rows must
    follow, adding the newly ticked and dropping the unticked."""
    cohort, sessions = await _make_cohort(db)
    user = await _make_instructor(db)
    call = await _open_cohort_call(db, cohort, sessions)

    await cohort_staffing.register_cohort_interest(
        db, cohort_id=cohort.id, cohort_call_id=call.id, user=user,
        session_ids=[sessions[0].id, sessions[1].id],
    )
    await cohort_staffing.register_cohort_interest(
        db, cohort_id=cohort.id, cohort_call_id=call.id, user=user,
        session_ids=[sessions[2].id],
    )
    per_session = (await db.execute(
        select(InstructorInterest.session_id).where(InstructorInterest.user_id == user.id)
    )).scalars().all()
    assert set(per_session) == {sessions[2].id}
    rows = (await db.execute(
        select(CohortCallInterest).where(CohortCallInterest.cohort_call_id == call.id)
    )).scalars().all()
    assert len(rows) == 1, "re-registering replaces, never duplicates"


@pytest.mark.asyncio
async def test_registering_with_no_valid_sessions_is_refused(db):
    cohort, sessions = await _make_cohort(db)
    user = await _make_instructor(db)
    call = await _open_cohort_call(db, cohort, sessions)

    with pytest.raises(HTTPException) as exc:
        await cohort_staffing.register_cohort_interest(
            db, cohort_id=cohort.id, cohort_call_id=call.id, user=user,
            session_ids=[uuid.uuid4()],
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_registering_for_a_second_role_speaks_to_the_instructor_directly(db):
    """The same 409 ops sees when assigning someone else says 'Ahmed is
    already X — remove the existing assignment' — actionable for ops, but
    an instructor hitting this about *themselves* can't remove anything and
    shouldn't be told about themselves in third person (2026-08-30 fix)."""
    cohort, sessions = await _make_cohort(db)
    user = await _make_instructor(db)
    lead, assistant = await _role_id(db, "Lead Facilitator"), await _role_id(db, "Assistant Facilitator")
    call = await _open_cohort_call(db, cohort, sessions)

    # A real assignment (ops already picked them for Lead), not just an
    # application — _assert_single_role checks assignments, not interest.
    await cohort_staffing.select_for_cohort(
        db, cohort_id=cohort.id, user_ids=[user.id], role_id=lead, session_ids=[sessions[0].id],
    )

    with pytest.raises(HTTPException) as exc:
        await cohort_staffing.register_cohort_interest(
            db, cohort_id=cohort.id, cohort_call_id=call.id, user=user,
            session_ids=[sessions[0].id], role_id=assistant,
        )
    assert exc.value.status_code == 409
    assert exc.value.detail.startswith("You're already Lead Facilitator")
    assert "remove the existing assignment" not in exc.value.detail
    assert user.full_name not in exc.value.detail


@pytest.mark.asyncio
async def test_withdrawing_clears_both_levels(db):
    cohort, sessions = await _make_cohort(db)
    user = await _make_instructor(db)
    call = await _open_cohort_call(db, cohort, sessions)

    await cohort_staffing.register_cohort_interest(
        db, cohort_id=cohort.id, cohort_call_id=call.id, user=user,
        session_ids=[s.id for s in sessions],
    )
    await cohort_staffing.withdraw_cohort_interest(
        db, cohort_id=cohort.id, cohort_call_id=call.id, user=user
    )
    assert (await db.execute(
        select(CohortCallInterest).where(CohortCallInterest.cohort_call_id == call.id)
    )).scalars().all() == []
    assert (await db.execute(
        select(InstructorInterest).where(InstructorInterest.user_id == user.id)
    )).scalars().all() == []


# ── selection: ticked days, and the rate snapshot ───────────────────────────

@pytest.mark.asyncio
async def test_selection_assigns_exactly_the_ticked_days(db):
    """Ticking 2 of 3 days gets a 2-day assignment, not the whole cohort."""
    cohort, sessions = await _make_cohort(db)
    user = await _make_instructor(db)
    lead = await _role_id(db)
    await _offer_role(db, cohort, lead)
    call = await _open_cohort_call(db, cohort, sessions)

    await cohort_staffing.register_cohort_interest(
        db, cohort_id=cohort.id, cohort_call_id=call.id, user=user,
        session_ids=[sessions[0].id, sessions[2].id], role_id=lead,
    )
    picked = await cohort_staffing.select_for_cohort(
        db, cohort_id=cohort.id, user_ids=[user.id], cohort_call_id=call.id,
    )
    assert set(picked[0]["session_ids"]) == {sessions[0].id, sessions[2].id}
    assigned = (await db.execute(
        select(SessionInstructor.session_id)
        .join(Session, Session.id == SessionInstructor.session_id)
        .where(Session.cohort_id == cohort.id, SessionInstructor.user_id == user.id)
    )).scalars().all()
    assert set(assigned) == {sessions[0].id, sessions[2].id}


@pytest.mark.asyncio
async def test_selection_uses_the_role_the_applicant_asked_for(db):
    cohort, sessions = await _make_cohort(db)
    user = await _make_instructor(db)
    assistant = await _role_id(db, "Assistant Facilitator")
    await _offer_role(db, cohort, assistant)
    call = await _open_cohort_call(db, cohort, sessions)

    await cohort_staffing.register_cohort_interest(
        db, cohort_id=cohort.id, cohort_call_id=call.id, user=user,
        session_ids=[sessions[0].id], role_id=assistant,
    )
    picked = await cohort_staffing.select_for_cohort(
        db, cohort_id=cohort.id, user_ids=[user.id], cohort_call_id=call.id,
    )
    assert picked[0]["role_id"] == assistant


@pytest.mark.asyncio
async def test_rate_is_snapshotted_and_survives_a_later_cohort_rate_edit(db):
    """The whole reason the assignment row carries a rate: editing the cohort
    opening next month must not reprice an assignment already agreed."""
    cohort, sessions = await _make_cohort(db)
    user = await _make_instructor(db)
    lead = await _role_id(db)
    db.add(CohortOpening(
        id=uuid.uuid4(), cohort_id=cohort.id, role_id=lead, slots=2, amount_aed=Decimal("500.00"),
    ))
    await db.flush()

    picked = await cohort_staffing.select_for_cohort(
        db, cohort_id=cohort.id, user_ids=[user.id], role_id=lead, session_ids=[sessions[0].id],
    )
    assert Decimal(str(picked[0]["rate_aed"])) == Decimal("500.00")

    opening = (await db.execute(
        select(CohortOpening).where(CohortOpening.cohort_id == cohort.id)
    )).scalars().one()
    opening.amount_aed = Decimal("900.00")
    await db.flush()

    await cohort_staffing.select_for_cohort(
        db, cohort_id=cohort.id, user_ids=[user.id], role_id=lead, session_ids=[sessions[1].id],
    )
    assignment = (await db.execute(
        select(CohortInstructorAssignment).where(
            CohortInstructorAssignment.cohort_id == cohort.id,
            CohortInstructorAssignment.user_id == user.id,
        )
    )).scalars().one()
    assert assignment.rate_aed == Decimal("500.00"), "an agreed rate must never be silently repriced"


@pytest.mark.asyncio
async def test_rate_falls_back_to_the_role_default(db):
    """Nothing set on the session or the cohort — the global tier answers."""
    cohort, sessions = await _make_cohort(db)
    user = await _make_instructor(db)
    lead = await _role_id(db)
    role = await db.get(DeliveryRole, lead)
    role.default_rate_aed = Decimal("275.00")
    db.add(CohortOpening(id=uuid.uuid4(), cohort_id=cohort.id, role_id=lead, slots=1, amount_aed=None))
    await db.flush()

    picked = await cohort_staffing.select_for_cohort(
        db, cohort_id=cohort.id, user_ids=[user.id], role_id=lead, session_ids=[sessions[0].id],
    )
    assert Decimal(str(picked[0]["rate_aed"])) == Decimal("275.00")


@pytest.mark.asyncio
async def test_removing_an_assignment_marks_it_withdrawn_and_drops_sessions(db):
    cohort, sessions = await _make_cohort(db)
    user = await _make_instructor(db)
    lead = await _role_id(db)

    await cohort_staffing.select_for_cohort(
        db, cohort_id=cohort.id, user_ids=[user.id], role_id=lead,
        session_ids=[s.id for s in sessions],
    )
    await cohort_staffing.remove_cohort_assignment(db, cohort_id=cohort.id, user_id=user.id)

    assignment = (await db.execute(
        select(CohortInstructorAssignment).where(
            CohortInstructorAssignment.cohort_id == cohort.id,
            CohortInstructorAssignment.user_id == user.id,
        )
    )).scalars().one()
    assert assignment.status == "withdrawn", "the record that they were staffed must survive"
    assigned = (await db.execute(
        select(SessionInstructor).join(Session, Session.id == SessionInstructor.session_id)
        .where(Session.cohort_id == cohort.id, SessionInstructor.user_id == user.id)
    )).scalars().all()
    assert assigned == []


@pytest.mark.asyncio
async def test_ops_applicant_table_is_one_row_per_instructor(db):
    cohort, sessions = await _make_cohort(db)
    a, b = await _make_instructor(db, "Muna A"), await _make_instructor(db, "Sara B")
    call = await _open_cohort_call(db, cohort, sessions)

    await cohort_staffing.register_cohort_interest(
        db, cohort_id=cohort.id, cohort_call_id=call.id, user=a,
        session_ids=[s.id for s in sessions], needs_transport=True,
    )
    await cohort_staffing.register_cohort_interest(
        db, cohort_id=cohort.id, cohort_call_id=call.id, user=b,
        session_ids=[sessions[0].id],
    )
    rows = await cohort_staffing.list_cohort_call_interest(
        db, cohort_id=cohort.id, cohort_call_id=call.id
    )
    assert len(rows) == 2
    by_name = {r["full_name"]: r for r in rows}
    assert by_name["Muna A"]["session_count"] == 3
    assert by_name["Muna A"]["needs_transport"] is True
    assert by_name["Sara B"]["session_count"] == 1
