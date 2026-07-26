"""Mandatory tests for V2 W5 S5-1 (see MASTER_EXECUTION_PLAN_V2.md):
assignment enforced in the query (not-assigned instructor -> 404, ops always
allowed), roster resolves the default-all/explicit-subset RegistrationSession
convention correctly, start_session/mark_done are idempotent, manual
attendance upserts rather than duplicating.
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration, RegistrationSession
from app.models.sessions.session import Session, SessionInstructor
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.sessions import delivery
from app.services.sessions.registration import register


async def _make_cohort_with_session(db, **overrides) -> tuple[Cohort, Session]:
    program = Program(
        id=uuid.uuid4(), code=f"DELIV-{uuid.uuid4().hex[:8]}", name="Delivery Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort_defaults = dict(
        id=uuid.uuid4(), program_id=program.id, name="Delivery Test Cohort",
        status="registration_open", visibility="public",
    )
    cohort_overrides = {k: overrides.pop(k) for k in list(overrides) if k in ("status",)}
    cohort_defaults.update(cohort_overrides)
    cohort = Cohort(**cohort_defaults)
    db.add(cohort)
    await db.flush()
    session_defaults = dict(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 10))
    session_defaults.update(overrides)
    session = Session(**session_defaults)
    db.add(session)
    await db.flush()
    return cohort, session


async def _make_registration(db, cohort: Cohort, *, name: str = "Test Student", session_ids=None) -> Registration:
    contact = Contact(
        id=uuid.uuid4(), full_name=name, contact_roles=["student"],
        secondary_phones=[], preferred_language="ar", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    return await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="form", session_ids=session_ids)


async def _make_user(db, roles: list[str], **overrides) -> User:
    defaults = dict(
        id=uuid.uuid4(), full_name="Test User", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=roles,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    return user


async def _assign(db, session: Session, user: User, role="lead"):
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=user.id, role=role))
    await db.flush()


# ── assignment enforcement ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unassigned_instructor_gets_404_not_403(db):
    _, session = await _make_cohort_with_session(db)
    instructor = await _make_user(db, ["instructor"])
    with pytest.raises(HTTPException) as exc:
        await delivery.get_roster(db, session.id, instructor)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_assigned_instructor_can_access(db):
    _, session = await _make_cohort_with_session(db)
    instructor = await _make_user(db, ["instructor"])
    await _assign(db, session, instructor)
    session_out, cohort_out, roster = await delivery.get_roster(db, session.id, instructor)
    assert session_out.id == session.id
    assert roster == []


@pytest.mark.asyncio
async def test_ops_always_allowed_without_assignment(db):
    _, session = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])
    session_out, _, _ = await delivery.get_roster(db, session.id, ops)
    assert session_out.id == session.id


# ── roster resolution (default-all vs explicit subset) ──────────────────────

@pytest.mark.asyncio
async def test_roster_includes_registration_with_no_session_restriction(db):
    cohort, session = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])
    reg = await _make_registration(db, cohort, name="Unrestricted Student")

    _, _, roster = await delivery.get_roster(db, session.id, ops)

    assert len(roster) == 1
    assert roster[0][1].full_name == "Unrestricted Student"
    assert roster[0][2] is None  # no attendance recorded yet


@pytest.mark.asyncio
async def test_roster_excludes_registration_restricted_to_other_session(db):
    cohort, session = await _make_cohort_with_session(db)
    other_session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 17))
    db.add(other_session)
    await db.flush()
    ops = await _make_user(db, ["operations"])
    await _make_registration(db, cohort, name="Other Session Student", session_ids=[other_session.id])

    _, _, roster = await delivery.get_roster(db, session.id, ops)
    assert roster == []


@pytest.mark.asyncio
async def test_roster_includes_registration_explicitly_covering_this_session(db):
    cohort, session = await _make_cohort_with_session(db)
    other_session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 17))
    db.add(other_session)
    await db.flush()
    ops = await _make_user(db, ["operations"])
    await _make_registration(db, cohort, name="Both Sessions Student", session_ids=[session.id, other_session.id])

    _, _, roster = await delivery.get_roster(db, session.id, ops)
    assert len(roster) == 1
    assert roster[0][1].full_name == "Both Sessions Student"


@pytest.mark.asyncio
async def test_roster_excludes_cancelled_registration(db):
    cohort, session = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])
    reg = await _make_registration(db, cohort, name="Cancelled Student")
    reg.status = "cancelled"
    await db.flush()

    _, _, roster = await delivery.get_roster(db, session.id, ops)
    assert roster == []


@pytest.mark.asyncio
async def test_roster_reflects_existing_attendance(db):
    cohort, session = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])
    reg = await _make_registration(db, cohort, name="Marked Student")
    db.add(AttendanceRecord(
        id=uuid.uuid4(), registration_id=reg.id, session_id=session.id,
        att_status="present", method="manual", recorded_by_user_id=ops.id,
    ))
    await db.flush()

    _, _, roster = await delivery.get_roster(db, session.id, ops)
    assert len(roster) == 1
    _, _, att = roster[0]
    assert att is not None
    assert att.att_status == "present"


# ── start_session / mark_done ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_session_sets_timestamp_and_flips_cohort_to_running(db):
    cohort, session = await _make_cohort_with_session(db, status="planned")
    ops = await _make_user(db, ["operations"])

    result = await delivery.start_session(db, session.id, ops)

    assert result.started_at is not None
    await db.refresh(cohort)
    assert cohort.status == "running"


@pytest.mark.asyncio
async def test_start_session_is_idempotent(db):
    _, session = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])

    first = await delivery.start_session(db, session.id, ops)
    second = await delivery.start_session(db, session.id, ops)

    assert first.started_at == second.started_at


@pytest.mark.asyncio
async def test_start_session_does_not_touch_completed_cohort_status(db):
    cohort, session = await _make_cohort_with_session(db, status="completed")
    ops = await _make_user(db, ["operations"])

    await delivery.start_session(db, session.id, ops)

    await db.refresh(cohort)
    assert cohort.status == "completed"


@pytest.mark.asyncio
async def test_mark_done_sets_timestamp_idempotently(db):
    _, session = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])

    first = await delivery.mark_done(db, session.id, ops)
    second = await delivery.mark_done(db, session.id, ops)

    assert first.completed_at is not None
    assert first.completed_at == second.completed_at


# ── mark_attendance (manual) ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_attendance_creates_new_record(db):
    cohort, session = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])
    reg = await _make_registration(db, cohort)

    record, contact = await delivery.mark_attendance(db, session.id, reg.id, "present", ops)

    assert record.att_status == "present"
    assert record.method == "manual"
    assert record.recorded_by_user_id == ops.id
    assert contact.full_name == "Test Student"


@pytest.mark.asyncio
async def test_mark_attendance_upserts_not_duplicates(db):
    cohort, session = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])
    reg = await _make_registration(db, cohort)

    await delivery.mark_attendance(db, session.id, reg.id, "absent", ops)
    record, _ = await delivery.mark_attendance(db, session.id, reg.id, "late", ops)

    from sqlalchemy import select
    rows = (await db.execute(
        select(AttendanceRecord).where(AttendanceRecord.registration_id == reg.id, AttendanceRecord.session_id == session.id)
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].att_status == "late"


@pytest.mark.asyncio
async def test_mark_attendance_rejects_registration_from_other_cohort(db):
    cohort_a, session_a = await _make_cohort_with_session(db)
    cohort_b, _ = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])
    reg_b = await _make_registration(db, cohort_b)

    with pytest.raises(HTTPException) as exc:
        await delivery.mark_attendance(db, session_a.id, reg_b.id, "present", ops)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_mark_attendance_requires_assignment_for_instructor(db):
    cohort, session = await _make_cohort_with_session(db)
    reg = await _make_registration(db, cohort)
    instructor = await _make_user(db, ["instructor"])  # not assigned

    with pytest.raises(HTTPException) as exc:
        await delivery.mark_attendance(db, session.id, reg.id, "present", instructor)
    assert exc.value.status_code == 404


# ── scan_attendance (QR, reuses check_in) ───────────────────────────────────

@pytest.mark.asyncio
async def test_scan_attendance_requires_assignment(db):
    cohort, session = await _make_cohort_with_session(db)
    reg = await _make_registration(db, cohort)
    instructor = await _make_user(db, ["instructor"])  # not assigned

    with pytest.raises(HTTPException) as exc:
        await delivery.scan_attendance(db, session.id, reg.ticket_token, instructor)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_scan_attendance_records_present_via_qr(db):
    cohort, session = await _make_cohort_with_session(db)
    reg = await _make_registration(db, cohort, name="Scanned Student")
    instructor = await _make_user(db, ["instructor"])
    await _assign(db, session, instructor)

    record, contact = await delivery.scan_attendance(db, session.id, reg.ticket_token, instructor)

    assert record.method == "qr"
    assert record.att_status == "present"
    assert contact.full_name == "Scanned Student"


# ── complete_cohort (basic status-flip only — full attendance-rate/
#    certificate coverage lives in test_complete_cohort.py, S5-3) ───────────

@pytest.mark.asyncio
async def test_complete_cohort_sets_status(db):
    cohort, _ = await _make_cohort_with_session(db, status="running")
    result = await delivery.complete_cohort(db, cohort.id, uuid.uuid4())
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_complete_cohort_404_for_unknown_cohort(db):
    with pytest.raises(HTTPException) as exc:
        await delivery.complete_cohort(db, uuid.uuid4(), uuid.uuid4())
    assert exc.value.status_code == 404
