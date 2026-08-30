"""Cohort-aggregated payment lines (2026-08-24).

The operator's letter should read

    10-14/10/2026   TDRA Camp   Lead Facilitator   Abu Dhabi   4 x 500   2,000

— a date *range*, and a count that an absence reduces. What this file pins:

  * the count is ops-approved present days, not assigned days;
  * the date cell is a range, never an itemised attended-day list;
  * accrual is idempotent, and a session on a cohort line never comes back;
  * paying the lead still leaves the assistant billable for the same days;
  * a second cohort lands on the same open draft letter, but never on one that
    has already been published or signed.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.enums import PaymentLetterStatus
from app.models.instructors.payment import PaymentLetter, PaymentSession
from app.models.sessions.checklist import InstructorSessionDay
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_assignment import CohortInstructorAssignment
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.payment_coverage import PaymentSessionCoverage
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.sessions import day as day_svc
from app.services.sessions import journey


async def _role(db, name="Lead Facilitator"):
    return await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))


async def _instructor(db, name="Muna A") -> User:
    user = User(
        id=uuid.uuid4(), full_name=name, email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=["instructor"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _cohort(db, *, days: int = 5, name="TDRA Camp"):
    program = Program(
        id=uuid.uuid4(), code=f"PAY-{uuid.uuid4().hex[:8]}", name="Pay Program",
        program_type="workshop", pricing_model="free", active=True,
        completion_rule_type="percentage", completion_rule_value=70,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name=name, status="running", visibility="public",
        starts_on=date(2026, 10, 10), ends_on=date(2026, 10, 10 + days - 1),
    )
    db.add(cohort)
    await db.flush()
    sessions = []
    for i in range(days):
        s = Session(
            id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 10, 10 + i),
            completed_at=datetime.now(timezone.utc),
        )
        db.add(s)
        sessions.append(s)
    await db.flush()
    return cohort, sessions


async def _staff(db, cohort, sessions, user, *, rate="500.00", role_name="Lead Facilitator"):
    role_id = await _role(db, role_name)
    for s in sessions:
        db.add(SessionInstructor(
            id=uuid.uuid4(), session_id=s.id, user_id=user.id, role_id=role_id,
        ))
    db.add(CohortInstructorAssignment(
        id=uuid.uuid4(), cohort_id=cohort.id, user_id=user.id, role_id=role_id,
        rate_basis="per_session", rate_aed=Decimal(rate) if rate else None, status="active",
    ))
    await db.flush()


async def _approve_days(db, sessions, user, ops, *, absent_on=()):
    for s in sessions:
        absent = s.id in absent_on
        await day_svc.check_in(
            db, s.id, user,
            att_status="absent" if absent else "present",
            reason="driving test" if absent else None,
        )
        await day_svc.submit_day(db, s.id, user)
    days = (await db.execute(
        select(InstructorSessionDay).where(
            InstructorSessionDay.session_id.in_([s.id for s in sessions]),
            InstructorSessionDay.user_id == user.id,
        )
    )).scalars().all()
    for d in days:
        await day_svc.approve_day(db, d.id, ops.id)


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ops", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


# ── the line itself ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_absence_reduces_the_count_not_the_date_range(db):
    """The operator's exact example: Muna misses one day of a five-day camp.
    The letter still says 10-14 October; it says 4 x 500, not 5 x 500."""
    cohort, sessions = await _cohort(db)
    user, ops = await _instructor(db), await _ops(db)
    await _staff(db, cohort, sessions, user)
    await _approve_days(db, sessions, user, ops, absent_on={sessions[2].id})

    lines = await journey.unbilled_cohorts(db, user.id)
    assert len(lines) == 1
    line = lines[0]
    assert line["session_count"] == 4
    assert line["rate_aed"] == 500.0
    assert line["compensation_aed"] == 2000.0
    assert line["session_date"] == "10/10/2026 - 14/10/2026", \
        "the range covers the cohort; the absence shows up in the count"
    assert line["role"] == "Lead Facilitator"


@pytest.mark.asyncio
async def test_the_range_is_the_cohorts_even_when_the_last_day_was_missed(db):
    """The operator was explicit: "the data in the payment is always the range
    of the cohort no matter which date you worked on". Shrinking the dates to
    the days actually delivered would leak which specific days somebody missed
    onto a document that deliberately does not itemise attendance."""
    cohort, sessions = await _cohort(db, days=5)
    user, ops = await _instructor(db), await _ops(db)
    await _staff(db, cohort, sessions, user)
    # Absent on the first AND last day — the two that would move a naive range.
    await _approve_days(db, sessions, user, ops, absent_on={sessions[0].id, sessions[4].id})

    line = (await journey.unbilled_cohorts(db, user.id))[0]
    assert line["session_date"] == "10/10/2026 - 14/10/2026"
    assert line["session_count"] == 3, "the absence shows up here, and only here"


@pytest.mark.asyncio
async def test_the_range_falls_back_to_the_sessions_when_cohort_dates_are_unset(db):
    cohort, sessions = await _cohort(db, days=3)
    cohort.starts_on = None
    cohort.ends_on = None
    await db.flush()
    user, ops = await _instructor(db), await _ops(db)
    await _staff(db, cohort, sessions, user)
    await _approve_days(db, sessions, user, ops, absent_on={sessions[2].id})

    line = (await journey.unbilled_cohorts(db, user.id))[0]
    assert line["session_date"] == "10/10/2026 - 12/10/2026", \
        "with no cohort dates set, the cohort's own sessions define the span"


@pytest.mark.asyncio
async def test_days_never_approved_do_not_count(db):
    """`completed_at` alone is not delivery — ops has to have signed it off."""
    cohort, sessions = await _cohort(db, days=3)
    user, ops = await _instructor(db), await _ops(db)
    await _staff(db, cohort, sessions, user)
    await _approve_days(db, sessions[:2], user, ops)
    # The third day was submitted but never reviewed.
    await day_svc.check_in(db, sessions[2].id, user, att_status="present")
    await day_svc.submit_day(db, sessions[2].id, user)

    line = (await journey.unbilled_cohorts(db, user.id))[0]
    assert line["session_count"] == 2
    assert line["compensation_aed"] == 1000.0


@pytest.mark.asyncio
async def test_a_single_day_line_prints_one_date_not_a_range(db):
    cohort, sessions = await _cohort(db, days=1)
    user, ops = await _instructor(db), await _ops(db)
    await _staff(db, cohort, sessions, user)
    await _approve_days(db, sessions, user, ops)

    line = (await journey.unbilled_cohorts(db, user.id))[0]
    assert line["session_date"] == "10/10/2026"


@pytest.mark.asyncio
async def test_a_flat_arrangement_ignores_the_count(db):
    cohort, sessions = await _cohort(db, days=5)
    user, ops = await _instructor(db), await _ops(db)
    await _staff(db, cohort, sessions, user, rate=None)
    assignment = (await db.execute(
        select(CohortInstructorAssignment).where(CohortInstructorAssignment.user_id == user.id)
    )).scalars().one()
    assignment.rate_basis = "flat"
    assignment.flat_amount_aed = Decimal("3000.00")
    await db.flush()
    await _approve_days(db, sessions, user, ops, absent_on={sessions[0].id})

    line = (await journey.unbilled_cohorts(db, user.id))[0]
    assert line["compensation_aed"] == 3000.0
    assert line["rate_aed"] is None


@pytest.mark.asyncio
async def test_pre_daily_loop_work_still_bills_off_completed_at(db):
    """Cohorts delivered before the daily loop existed have no day rows. They
    must stay billable rather than silently dropping to zero."""
    cohort, sessions = await _cohort(db, days=3)
    user = await _instructor(db)
    await _staff(db, cohort, sessions, user)

    line = (await journey.unbilled_cohorts(db, user.id))[0]
    assert line["session_count"] == 3


# ── accrual ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_accrual_writes_one_draft_line_with_coverage(db):
    cohort, sessions = await _cohort(db)
    user, ops = await _instructor(db), await _ops(db)
    await _staff(db, cohort, sessions, user)
    await _approve_days(db, sessions, user, ops, absent_on={sessions[1].id})

    written = await journey.accrue_cohort_pay(db, cohort.id)
    assert len(written) == 1
    row = written[0]
    assert row.session_count == 4
    assert row.compensation_aed == 2000.0
    assert row.rate_aed == 500.0
    assert row.cohort_id == cohort.id
    assert row.session_id is None, "a cohort line names no single session"

    covered = (await db.execute(
        select(PaymentSessionCoverage.session_id)
        .where(PaymentSessionCoverage.payment_session_id == row.id)
    )).scalars().all()
    assert len(covered) == 4
    assert sessions[1].id not in covered, "the absent day is not covered by the line"

    letter = await db.get(PaymentLetter, row.payment_letter_id)
    assert letter.status == PaymentLetterStatus.draft


@pytest.mark.asyncio
async def test_accrual_is_idempotent(db):
    cohort, sessions = await _cohort(db, days=2)
    user, ops = await _instructor(db), await _ops(db)
    await _staff(db, cohort, sessions, user)
    await _approve_days(db, sessions, user, ops)

    assert len(await journey.accrue_cohort_pay(db, cohort.id)) == 1
    assert await journey.accrue_cohort_pay(db, cohort.id) == [], \
        "running it twice must not write a second line"
    rows = (await db.execute(select(PaymentSession))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_a_billed_cohort_drops_off_the_unbilled_list(db):
    cohort, sessions = await _cohort(db, days=2)
    user, ops = await _instructor(db), await _ops(db)
    await _staff(db, cohort, sessions, user)
    await _approve_days(db, sessions, user, ops)

    await journey.accrue_cohort_pay(db, cohort.id)
    assert await journey.unbilled_cohorts(db, user.id) == []
    assert await journey.unbilled_sessions(db, user.id) == [], \
        "the covered sessions must not reappear as leftover single lines"


@pytest.mark.asyncio
async def test_paying_the_lead_leaves_the_assistant_still_billable(db):
    """One session is delivered by several people, each paid separately. This
    is the bug the instructor-scoped rule was written for — it has to survive
    the move to coverage rows."""
    cohort, sessions = await _cohort(db, days=2)
    lead, assistant, ops = await _instructor(db, "Lead"), await _instructor(db, "Assistant"), await _ops(db)
    await _staff(db, cohort, sessions, lead, rate="500.00", role_name="Lead Facilitator")
    await _staff(db, cohort, sessions, assistant, rate="300.00", role_name="Assistant Facilitator")
    await _approve_days(db, sessions, lead, ops)
    await _approve_days(db, sessions, assistant, ops)

    await journey.accrue_cohort_pay(db, cohort.id)
    lead_rows = await journey.unbilled_cohorts(db, lead.id)
    assistant_rows = await journey.unbilled_cohorts(db, assistant.id)
    assert lead_rows == [] and assistant_rows == []

    # Both got their own line, at their own rate.
    rows = (await db.execute(select(PaymentSession))).scalars().all()
    assert sorted(r.compensation_aed for r in rows) == [600.0, 1000.0]


@pytest.mark.asyncio
async def test_a_second_cohort_lands_on_the_same_open_draft(db):
    """Monthly aggregation: this is what keeps one instructor to one bank
    transaction."""
    user, ops = await _instructor(db), await _ops(db)
    for name in ("TDRA Camp", "Quick Flight"):
        cohort, sessions = await _cohort(db, days=2, name=name)
        await _staff(db, cohort, sessions, user)
        await _approve_days(db, sessions, user, ops)
        await journey.accrue_cohort_pay(db, cohort.id)

    letters = (await db.execute(select(PaymentLetter))).scalars().all()
    assert len(letters) == 1, "both cohorts belong on one monthly letter"
    rows = (await db.execute(select(PaymentSession))).scalars().all()
    assert len(rows) == 2
    assert {r.workshop_description for r in rows} == {"TDRA Camp", "Quick Flight"}
    assert sorted(r.sort_order for r in rows) == [1, 2]


@pytest.mark.asyncio
async def test_a_published_letter_is_not_appended_to(db):
    """A published letter is being signed; a signed one is a document somebody
    put their name to. Later work starts a fresh draft."""
    user, ops = await _instructor(db), await _ops(db)
    cohort, sessions = await _cohort(db, days=2, name="First")
    await _staff(db, cohort, sessions, user)
    await _approve_days(db, sessions, user, ops)
    await journey.accrue_cohort_pay(db, cohort.id)

    letter = (await db.execute(select(PaymentLetter))).scalars().one()
    letter.status = PaymentLetterStatus.published
    await db.flush()

    cohort2, sessions2 = await _cohort(db, days=2, name="Second")
    await _staff(db, cohort2, sessions2, user)
    await _approve_days(db, sessions2, user, ops)
    await journey.accrue_cohort_pay(db, cohort2.id)

    letters = (await db.execute(select(PaymentLetter))).scalars().all()
    assert len(letters) == 2
    drafts = [le for le in letters if le.status == PaymentLetterStatus.draft]
    assert len(drafts) == 1


@pytest.mark.asyncio
async def test_completing_a_cohort_does_not_draft_pay_automatically(db):
    """Reversed 2026-08-30: a completed cohort's work becomes billable — it
    shows up on the payments to-do list — but nothing gets drafted until ops
    explicitly clicks "Create letter". Auto-drafting the moment the last
    report was approved meant a letter existed before anyone decided it
    should."""
    cohort, sessions = await _cohort(db, days=2)
    user, ops = await _instructor(db), await _ops(db)
    await _staff(db, cohort, sessions, user)
    await _approve_days(db, sessions, user, ops)

    fired = await day_svc.maybe_complete_cohort(db, cohort.id, ops.id)
    assert fired is True
    await db.refresh(cohort)
    assert cohort.status == "completed"

    assert (await db.execute(select(PaymentSession))).scalars().all() == []
    assert (await db.execute(select(PaymentLetter))).scalars().all() == []

    todo = await journey.pending_payment_instructors(db)
    mine = next(r for r in todo if r["instructor_user_id"] == user.id)
    assert mine["pending_cohort_count"] == 1


@pytest.mark.asyncio
async def test_the_todo_list_counts_cohorts(db):
    user, ops = await _instructor(db), await _ops(db)
    cohort, sessions = await _cohort(db, days=3)
    await _staff(db, cohort, sessions, user)
    await _approve_days(db, sessions, user, ops)

    todo = await journey.pending_payment_instructors(db)
    mine = next(r for r in todo if r["instructor_user_id"] == user.id)
    assert mine["pending_cohort_count"] == 1
    assert mine["pending_session_count"] == 3
    assert mine["earliest_date"] == date(2026, 10, 10)
    assert mine["latest_date"] == date(2026, 10, 12)
