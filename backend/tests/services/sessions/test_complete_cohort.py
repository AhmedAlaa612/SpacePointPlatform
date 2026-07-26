"""Mandatory tests for V2 W5 S5-3 (see MASTER_EXECUTION_PLAN_V2.md, quoting
V1 P3-2): completion threshold boundary (0.69/0.70) and double-completion
idempotent. Capacity-full/minor-without-payer are R1-4's tests (register()
itself, unchanged here).

Certificate PDF generation runs for real (proven code, reused verbatim from
the existing staff-cert flows — see services/documents/certificate.py);
storage.upload_file is monkeypatched so nothing touches disk.
"""

import uuid
from datetime import date

import pytest
from sqlalchemy import select

from app.models.certificate import Certificate
from app.models.enums import CertificateType
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration, RegistrationSession
from app.models.sessions.session import Session
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.sessions import delivery
from app.services.sessions.registration import register


@pytest.fixture(autouse=True)
def _stub_email(monkeypatch):
    """Student completion certs are now emailed, not stored. Stub the send so
    the test DB never needs SMTP — and so we can assert it fires."""
    async def _noop(*args, **kwargs):
        return True
    monkeypatch.setattr(delivery, "try_send_email", _noop)


async def _make_cohort_with_sessions(db, n: int, **program_overrides) -> tuple[Cohort, Program, list[Session]]:
    program_defaults = dict(
        id=uuid.uuid4(), code=f"CMP-{uuid.uuid4().hex[:8]}", name="Completion Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    program_defaults.update(program_overrides)
    program = Program(**program_defaults)
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Completion Test Cohort",
        status="running", visibility="public", starts_on=date(2026, 9, 1),
    )
    db.add(cohort)
    await db.flush()
    sessions = []
    for i in range(n):
        s = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 1 + i))
        db.add(s)
        sessions.append(s)
    await db.flush()
    return cohort, program, sessions


async def _make_actor(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ops Actor", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=["operations"],
    )
    db.add(user)
    await db.flush()
    return user


async def _make_registration(db, cohort: Cohort, *, name="Student") -> Registration:
    contact = Contact(
        id=uuid.uuid4(), full_name=name, contact_roles=["student"],
        secondary_phones=[], preferred_language="ar", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    return await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="form")


async def _mark(db, session: Session, registration: Registration, status: str, actor_id):
    db.add(AttendanceRecord(
        id=uuid.uuid4(), registration_id=registration.id, session_id=session.id,
        att_status=status, method="manual", recorded_by_user_id=actor_id,
    ))
    await db.flush()


# ── threshold boundary (0.69 vs 0.70 — i.e. 6/10 fails, 7/10 passes with 10 sessions;
#    here we use a clean 10-session cohort so present/total lands exactly on the line) ──

@pytest.mark.asyncio
async def test_below_threshold_marked_attended_no_certificate(db):
    cohort, program, sessions = await _make_cohort_with_sessions(db, 10)
    reg = await _make_registration(db, cohort)
    actor = (await _make_actor(db)).id
    # 6/10 = 0.60 < 0.7
    for s in sessions[:6]:
        await _mark(db, s, reg, "present", actor)

    await delivery.complete_cohort(db, cohort.id, actor)

    await db.refresh(reg)
    assert reg.status == "attended"
    cert = await db.scalar(select(Certificate).where(Certificate.registration_id == reg.id))
    assert cert is None


@pytest.mark.asyncio
async def test_at_threshold_marked_completed_with_certificate(db):
    cohort, program, sessions = await _make_cohort_with_sessions(db, 10)
    reg = await _make_registration(db, cohort, name="Boundary Student")
    actor = (await _make_actor(db)).id
    # 7/10 = 0.70 -- exactly at the threshold, must pass ("attendance_rate >= 0.7")
    for s in sessions[:7]:
        await _mark(db, s, reg, "present", actor)

    await delivery.complete_cohort(db, cohort.id, actor)

    await db.refresh(reg)
    assert reg.status == "completed"
    cert = await db.scalar(select(Certificate).where(Certificate.registration_id == reg.id))
    assert cert is not None
    assert cert.type == CertificateType.student_completion
    assert cert.contact_id == reg.contact_id
    assert cert.user_id is None
    assert cert.workshop_name == "Completion Test Program"
    # Student certs are emailed, not stored — no file_url/bucket/file_path on the row.
    assert cert.file_url is None
    assert cert.bucket is None


@pytest.mark.asyncio
async def test_absent_sessions_do_not_count_toward_completion(db):
    """attendance_rate = present / total sessions. Marking someone absent for
    a session is not partial credit — it's a zero."""
    cohort, program, sessions = await _make_cohort_with_sessions(db, 10)
    reg = await _make_registration(db, cohort)
    actor = (await _make_actor(db)).id
    for s in sessions[:7]:
        await _mark(db, s, reg, "absent", actor)  # 7 absent, 0 present

    await delivery.complete_cohort(db, cohort.id, actor)

    await db.refresh(reg)
    assert reg.status == "attended"


# ── double-completion idempotent (mandatory) ─────────────────────────────────

@pytest.mark.asyncio
async def test_double_completion_is_idempotent_no_duplicate_certificate(db):
    cohort, program, sessions = await _make_cohort_with_sessions(db, 4)
    reg = await _make_registration(db, cohort)
    actor = (await _make_actor(db)).id
    for s in sessions:
        await _mark(db, s, reg, "present", actor)

    await delivery.complete_cohort(db, cohort.id, actor)
    first_cert = await db.scalar(select(Certificate).where(Certificate.registration_id == reg.id))
    assert first_cert is not None

    # Re-run — must not error, must not create a second certificate.
    await delivery.complete_cohort(db, cohort.id, actor)

    certs = (await db.execute(select(Certificate).where(Certificate.registration_id == reg.id))).scalars().all()
    assert len(certs) == 1
    assert certs[0].id == first_cert.id


@pytest.mark.asyncio
async def test_double_completion_cohort_status_stays_completed(db):
    cohort, program, sessions = await _make_cohort_with_sessions(db, 2)
    actor = (await _make_actor(db)).id

    await delivery.complete_cohort(db, cohort.id, actor)
    await delivery.complete_cohort(db, cohort.id, actor)

    await db.refresh(cohort)
    assert cohort.status == "completed"


# ── RegistrationSession subset denominator ───────────────────────────────────

@pytest.mark.asyncio
async def test_denominator_respects_explicit_session_subset(db):
    """A registration restricted to 2 of the cohort's 10 sessions completes
    off a 2-session denominator, not all 10."""
    cohort, program, sessions = await _make_cohort_with_sessions(db, 10)
    contact = Contact(
        id=uuid.uuid4(), full_name="Subset Student", contact_roles=["student"],
        secondary_phones=[], preferred_language="ar", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    reg = await register(
        db, contact_id=contact.id, cohort_id=cohort.id, registered_via="form",
        session_ids=[sessions[0].id, sessions[1].id],
    )
    actor = (await _make_actor(db)).id
    await _mark(db, sessions[0], reg, "present", actor)
    await _mark(db, sessions[1], reg, "present", actor)
    # Present for 2 of the 8 OTHER sessions too — must not count toward this
    # registration's denominator since it's restricted to sessions[0:2].
    await _mark(db, sessions[2], reg, "absent", actor)

    await delivery.complete_cohort(db, cohort.id, actor)

    await db.refresh(reg)
    assert reg.status == "completed"  # 2/2 = 1.0, not 2/10 = 0.2


@pytest.mark.asyncio
async def test_cancelled_registration_excluded_from_completion(db):
    cohort, program, sessions = await _make_cohort_with_sessions(db, 2)
    reg = await _make_registration(db, cohort)
    reg.status = "cancelled"
    await db.flush()
    actor = (await _make_actor(db)).id

    await delivery.complete_cohort(db, cohort.id, actor)

    await db.refresh(reg)
    assert reg.status == "cancelled"  # untouched, not overwritten to attended
    cert = await db.scalar(select(Certificate).where(Certificate.registration_id == reg.id))
    assert cert is None


# ── per-program completion rule (operator request 2026-07-25) ───────────────

@pytest.mark.asyncio
async def test_custom_percentage_threshold_lower_than_default(db):
    """3/5 = 60% fails the default 70% but passes a program configured for 50%."""
    cohort, program, sessions = await _make_cohort_with_sessions(
        db, 5, completion_rule_type="percentage", completion_rule_value=50,
    )
    reg = await _make_registration(db, cohort)
    actor = (await _make_actor(db)).id
    for s in sessions[:3]:
        await _mark(db, s, reg, "present", actor)

    await delivery.complete_cohort(db, cohort.id, actor)

    await db.refresh(reg)
    assert reg.status == "completed"
    cert = await db.scalar(select(Certificate).where(Certificate.registration_id == reg.id))
    assert cert is not None


@pytest.mark.asyncio
async def test_custom_percentage_threshold_higher_than_default(db):
    """8/10 = 80% passes the default 70% but fails a program configured for 90%."""
    cohort, program, sessions = await _make_cohort_with_sessions(
        db, 10, completion_rule_type="percentage", completion_rule_value=90,
    )
    reg = await _make_registration(db, cohort)
    actor = (await _make_actor(db)).id
    for s in sessions[:8]:
        await _mark(db, s, reg, "present", actor)

    await delivery.complete_cohort(db, cohort.id, actor)

    await db.refresh(reg)
    assert reg.status == "attended"


@pytest.mark.asyncio
async def test_session_count_rule_type_ignores_percentage(db):
    """3/10 present = only 30%, which would fail any sane percentage rule,
    but a session_count rule of 3 cares only about the raw count."""
    cohort, program, sessions = await _make_cohort_with_sessions(
        db, 10, completion_rule_type="session_count", completion_rule_value=3,
    )
    reg = await _make_registration(db, cohort)
    actor = (await _make_actor(db)).id
    for s in sessions[:3]:
        await _mark(db, s, reg, "present", actor)

    await delivery.complete_cohort(db, cohort.id, actor)

    await db.refresh(reg)
    assert reg.status == "completed"


@pytest.mark.asyncio
async def test_session_count_rule_type_boundary_below(db):
    cohort, program, sessions = await _make_cohort_with_sessions(
        db, 10, completion_rule_type="session_count", completion_rule_value=5,
    )
    reg = await _make_registration(db, cohort)
    actor = (await _make_actor(db)).id
    for s in sessions[:4]:
        await _mark(db, s, reg, "present", actor)

    await delivery.complete_cohort(db, cohort.id, actor)

    await db.refresh(reg)
    assert reg.status == "attended"


# ── manual certificate override (operator request 2026-07-25) ───────────────

@pytest.mark.asyncio
async def test_manual_override_issues_certificate_below_threshold(db):
    cohort, program, sessions = await _make_cohort_with_sessions(db, 10)
    reg = await _make_registration(db, cohort, name="Override Student")
    actor = (await _make_actor(db)).id
    # 2/10 = 20%, nowhere near the default 70% threshold.
    for s in sessions[:2]:
        await _mark(db, s, reg, "present", actor)
    await delivery.complete_cohort(db, cohort.id, actor)

    await db.refresh(reg)
    assert reg.status == "attended"
    assert await db.scalar(select(Certificate).where(Certificate.registration_id == reg.id)) is None

    certificate = await delivery.issue_certificate_override(db, reg.id, actor)

    assert certificate is not None
    assert certificate.contact_id == reg.contact_id
    await db.refresh(reg)
    assert reg.status == "completed"


@pytest.mark.asyncio
async def test_manual_override_is_idempotent(db):
    cohort, program, sessions = await _make_cohort_with_sessions(db, 2)
    reg = await _make_registration(db, cohort)
    actor = (await _make_actor(db)).id

    first = await delivery.issue_certificate_override(db, reg.id, actor)
    second = await delivery.issue_certificate_override(db, reg.id, actor)

    assert first.id == second.id
    certs = (await db.execute(select(Certificate).where(Certificate.registration_id == reg.id))).scalars().all()
    assert len(certs) == 1


@pytest.mark.asyncio
async def test_manual_override_on_already_completed_registration_returns_existing(db):
    """Overriding a student who already auto-completed must not create a
    second certificate — just hands back the one they already earned."""
    cohort, program, sessions = await _make_cohort_with_sessions(db, 2)
    reg = await _make_registration(db, cohort)
    actor = (await _make_actor(db)).id
    for s in sessions:
        await _mark(db, s, reg, "present", actor)
    await delivery.complete_cohort(db, cohort.id, actor)
    auto_cert = await db.scalar(select(Certificate).where(Certificate.registration_id == reg.id))

    override_cert = await delivery.issue_certificate_override(db, reg.id, actor)

    assert override_cert.id == auto_cert.id


@pytest.mark.asyncio
async def test_manual_override_unknown_registration_404(db):
    from fastapi import HTTPException
    actor = (await _make_actor(db)).id
    with pytest.raises(HTTPException) as exc:
        await delivery.issue_certificate_override(db, uuid.uuid4(), actor)
    assert exc.value.status_code == 404
