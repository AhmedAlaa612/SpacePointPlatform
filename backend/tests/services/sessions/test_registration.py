"""Mandatory tests for V2 R1-4 (see MASTER_EXECUTION_PLAN_V2.md R1-4):
capacity full; duplicate registration; check-in unknown/wrong-cohort/double/
not-covered-by-registration.
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.spine.contact import Contact
from app.models.spine.touchpoint import Touchpoint
from app.models.user import User
from app.services.sessions.registration import check_in, register


async def _make_staff_user(db) -> User:
    """attendance_records.recorded_by_user_id is NOT NULL — a real staff user
    always did the scan/mark, so tests need a real row to reference, not None."""
    user = User(
        id=uuid.uuid4(), full_name="Staff Member", email=f"staff-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"],
    )
    db.add(user)
    await db.flush()
    return user


def _new_contact(**overrides) -> Contact:
    defaults = dict(
        id=uuid.uuid4(), full_name="Test Student", contact_roles=["student"],
        secondary_phones=[], preferred_language="ar", lifecycle_stage="lead",
    )
    defaults.update(overrides)
    return Contact(**defaults)


async def _make_cohort(db, *, capacity=None, pricing_model="free", price=None) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"TEST-{uuid.uuid4().hex[:8]}", name="Test Program",
        program_type="workshop", pricing_model=pricing_model, price=price, active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Test Cohort",
        status="registration_open", visibility="public",
        capacity=capacity, starts_on=date(2026, 8, 1),
    )
    db.add(cohort)
    await db.flush()
    return cohort


# ── register(): mandatory cases ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_capacity_full_raises_409(db):
    cohort = await _make_cohort(db, capacity=1)
    first = _new_contact(full_name="First Student")
    second = _new_contact(full_name="Second Student")
    db.add_all([first, second])
    await db.flush()

    await register(db, contact_id=first.id, cohort_id=cohort.id, registered_via="form")

    with pytest.raises(HTTPException) as exc_info:
        await register(db, contact_id=second.id, cohort_id=cohort.id, registered_via="form")
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_register_with_payer_contact_succeeds(db):
    """A guardian/payer can be set on any registration regardless of the
    student's age — this system doesn't track or enforce minor status at
    all (see MASTER_EXECUTION_PLAN.md); a payer is just an optional field."""
    cohort = await _make_cohort(db)
    student = _new_contact(full_name="Student")
    guardian = _new_contact(full_name="Parent", contact_roles=["parent_guardian"])
    db.add_all([student, guardian])
    await db.flush()

    registration = await register(
        db, contact_id=student.id, cohort_id=cohort.id, payer_contact_id=guardian.id, registered_via="form"
    )
    assert registration.payer_contact_id == guardian.id


@pytest.mark.asyncio
async def test_duplicate_registration_raises_409(db):
    cohort = await _make_cohort(db)
    contact = _new_contact()
    db.add(contact)
    await db.flush()

    await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="form")

    with pytest.raises(HTTPException) as exc_info:
        await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="form")
    assert exc_info.value.status_code == 409


# ── register(): a few extra cases worth locking in ──────────────────────────

@pytest.mark.asyncio
async def test_free_program_waives_payment_paid_program_defaults_unpaid(db):
    free_cohort = await _make_cohort(db, pricing_model="free")
    paid_cohort = await _make_cohort(db, pricing_model="paid", price=100)
    contact_a = _new_contact(full_name="A")
    contact_b = _new_contact(full_name="B")
    db.add_all([contact_a, contact_b])
    await db.flush()

    free_reg = await register(db, contact_id=contact_a.id, cohort_id=free_cohort.id, registered_via="form")
    paid_reg = await register(db, contact_id=contact_b.id, cohort_id=paid_cohort.id, registered_via="form")

    assert free_reg.payment_status == "waived"
    assert paid_reg.payment_status == "unpaid"


@pytest.mark.asyncio
async def test_register_generates_unique_ticket_token_and_writes_touchpoint(db):
    cohort = await _make_cohort(db)
    contact = _new_contact()
    db.add(contact)
    await db.flush()

    registration = await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="form")

    assert registration.ticket_token and len(registration.ticket_token) > 20
    result = await db.execute(
        select(Touchpoint).where(Touchpoint.contact_id == contact.id, Touchpoint.touchpoint_type == "registration")
    )
    touchpoint = result.scalars().first()
    assert touchpoint is not None
    assert touchpoint.channel == "web"  # registered_via='form' -> channel='web'


@pytest.mark.asyncio
async def test_register_with_session_ids_writes_registration_sessions(db):
    cohort = await _make_cohort(db)
    staff = await _make_staff_user(db)
    session_a = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 1))
    session_b = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 8))
    db.add_all([session_a, session_b])
    await db.flush()
    contact = _new_contact()
    db.add(contact)
    await db.flush()

    registration = await register(
        db, contact_id=contact.id, cohort_id=cohort.id, registered_via="form", session_ids=[session_a.id],
    )

    with pytest.raises(HTTPException) as exc_info:
        await check_in(db, token=registration.ticket_token, session_id=session_b.id, actor_user_id=staff.id)
    assert exc_info.value.status_code == 409

    record = await check_in(db, token=registration.ticket_token, session_id=session_a.id, actor_user_id=staff.id)
    assert record.att_status == "present"


# ── check_in(): mandatory cases ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_in_unknown_token_raises_404(db):
    cohort = await _make_cohort(db)
    staff = await _make_staff_user(db)
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 1))
    db.add(session)
    await db.flush()

    with pytest.raises(HTTPException) as exc_info:
        await check_in(db, token="does-not-exist", session_id=session.id, actor_user_id=staff.id)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_check_in_wrong_cohort_raises_409(db):
    cohort_a = await _make_cohort(db)
    cohort_b = await _make_cohort(db)
    staff = await _make_staff_user(db)
    contact = _new_contact()
    db.add(contact)
    await db.flush()
    registration = await register(db, contact_id=contact.id, cohort_id=cohort_a.id, registered_via="form")

    other_session = Session(id=uuid.uuid4(), cohort_id=cohort_b.id, meeting_date=date(2026, 8, 1))
    db.add(other_session)
    await db.flush()

    with pytest.raises(HTTPException) as exc_info:
        await check_in(db, token=registration.ticket_token, session_id=other_session.id, actor_user_id=staff.id)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_check_in_already_recorded_raises_409(db):
    cohort = await _make_cohort(db)
    staff = await _make_staff_user(db)
    contact = _new_contact()
    db.add(contact)
    await db.flush()
    registration = await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="form")
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 1))
    db.add(session)
    await db.flush()

    first = await check_in(db, token=registration.ticket_token, session_id=session.id, actor_user_id=staff.id)
    assert first.att_status == "present"
    assert first.method == "qr"

    with pytest.raises(HTTPException) as exc_info:
        await check_in(db, token=registration.ticket_token, session_id=session.id, actor_user_id=staff.id)
    assert exc_info.value.status_code == 409
