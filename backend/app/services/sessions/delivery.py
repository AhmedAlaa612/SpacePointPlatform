"""Instructor session delivery (V2 W5 S5-1): roster, manual + QR attendance,
start/mark-done. Session-scoped throughout, matching W4's staffing model —
assignment lives on SessionInstructor, not on the cohort.

Every function here enforces "the assigned instructor, or ops/admin" itself
(via _get_deliverable_session), rather than leaving it to the router, so the
same rule can't drift between endpoints. Not-assigned is a 404 ("session not
found"), not a 403 — matches this codebase's existing "don't leak existence"
convention (see checkin.py, cohorts.py).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from html import escape
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.certificate import Certificate
from app.models.document_template import DocumentTemplate
from app.models.enums import CertificateType
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration, RegistrationSession
from app.models.sessions.session import Session, SessionInstructor
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.documents.certificate import generate_completion_certificate_pdf
from app.services.email import try_send_email
from app.services.sessions.registration import check_in, format_cohort_dates
from app.services.sessions.staffing import resolve_session_location_display


async def _get_deliverable_session(db: AsyncSession, session_id: UUID, user: User) -> Session:
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    if "operations" in user.role_values or "admin" in user.role_values:
        return session
    assigned = await db.scalar(
        select(SessionInstructor).where(
            SessionInstructor.session_id == session_id, SessionInstructor.user_id == user.id,
        )
    )
    if assigned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    return session


async def get_roster(
    db: AsyncSession, session_id: UUID, user: User,
) -> tuple[Session, Cohort, list[tuple[Registration, Contact, AttendanceRecord | None]]]:
    session = await _get_deliverable_session(db, session_id, user)
    cohort = await db.get(Cohort, session.cohort_id)

    # A registration covers this session if it has an explicit RegistrationSession
    # row for it, OR has no RegistrationSession rows at all (default = every
    # session in the cohort) — same rule check_in() enforces, restated here as
    # a set query instead of a per-registration check.
    covers_this_session = exists().where(
        RegistrationSession.registration_id == Registration.id,
        RegistrationSession.session_id == session_id,
    )
    has_any_restriction = exists().where(RegistrationSession.registration_id == Registration.id)

    rows = (await db.execute(
        select(Registration, Contact, AttendanceRecord)
        .join(Contact, Contact.id == Registration.contact_id)
        .outerjoin(AttendanceRecord, (AttendanceRecord.registration_id == Registration.id)
                   & (AttendanceRecord.session_id == session_id))
        .where(
            Registration.cohort_id == session.cohort_id,
            Registration.status != "cancelled",
            covers_this_session | ~has_any_restriction,
        )
        .order_by(Contact.full_name.asc())
    )).all()
    return session, cohort, [(reg, contact, att) for reg, contact, att in rows]


async def start_session(db: AsyncSession, session_id: UUID, user: User) -> Session:
    """Idempotent — tapping "start" twice (a real risk on a flaky 3G
    connection, per the mobile-first spec) must not error, just no-op past
    the first tap."""
    session = await _get_deliverable_session(db, session_id, user)
    if session.started_at is None:
        session.started_at = datetime.now(timezone.utc)
        cohort = await db.get(Cohort, session.cohort_id)
        if cohort.status in ("planned", "registration_open"):
            cohort.status = "running"
        await db.flush()
    return session


async def mark_done(db: AsyncSession, session_id: UUID, user: User) -> Session:
    """Idempotent, same reasoning as start_session.

    Kit counting is optional (operator request 2026-08-02): instructors can
    complete and close out the session regardless of whether kit post-checks
    have been performed.
    """
    session = await _get_deliverable_session(db, session_id, user)
    if session.completed_at is None:
        session.completed_at = datetime.now(timezone.utc)
        await db.flush()
    return session


async def mark_attendance(
    db: AsyncSession, session_id: UUID, registration_id: UUID, att_status: str, user: User,
) -> tuple[AttendanceRecord, Contact]:
    session = await _get_deliverable_session(db, session_id, user)
    registration = await db.get(Registration, registration_id)
    if registration is None or registration.cohort_id != session.cohort_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Registration not found for this session")

    existing = await db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.registration_id == registration_id, AttendanceRecord.session_id == session_id,
        )
    )
    if existing is not None:
        existing.att_status = att_status
        existing.method = "manual"
        existing.recorded_by_user_id = user.id
        existing.recorded_at = datetime.now(timezone.utc)
        record = existing
    else:
        record = AttendanceRecord(
            id=uuid4(), registration_id=registration_id, session_id=session_id,
            att_status=att_status, method="manual", recorded_by_user_id=user.id,
        )
        db.add(record)
    await db.flush()

    contact = await db.get(Contact, registration.contact_id)
    return record, contact


async def scan_attendance(db: AsyncSession, session_id: UUID, token: str, user: User) -> tuple[AttendanceRecord, Contact]:
    await _get_deliverable_session(db, session_id, user)
    record = await check_in(db, token=token, session_id=session_id, actor_user_id=user.id)
    registration = await db.get(Registration, record.registration_id)
    contact = await db.get(Contact, registration.contact_id)
    return record, contact


async def _sessions_covered(db: AsyncSession, cohort_id: UUID, registration_id: UUID) -> int:
    """"Total meetings" for the completion-rate denominator — respects the
    same default-all-if-unrestricted RegistrationSession convention as
    get_roster/check_in, just counting instead of filtering a roster."""
    restricted_ids = (await db.scalars(
        select(RegistrationSession.session_id).where(RegistrationSession.registration_id == registration_id)
    )).all()
    if restricted_ids:
        return len(restricted_ids)
    return await db.scalar(
        select(func.count()).select_from(Session).where(Session.cohort_id == cohort_id)
    ) or 0


async def _present_count(db: AsyncSession, registration_id: UUID) -> int:
    # attendance_rate = present / total sessions. With attendance now binary
    # (present|absent), this is simply the count of sessions attended.
    return await db.scalar(
        select(func.count()).select_from(AttendanceRecord).where(
            AttendanceRecord.registration_id == registration_id, AttendanceRecord.att_status == "present",
        )
    ) or 0


def _meets_completion_rule(program: Program, present: int, total: int) -> bool:
    """Per-program completion requirement (operator request 2026-07-25 —
    was a hardcoded global 0.7 from V1 P3-2; now admin-configurable per
    program, as either a percentage of sessions attended or an absolute
    session count)."""
    if program.completion_rule_type == "session_count":
        return present >= int(program.completion_rule_value)
    # "percentage" (default) — completion_rule_value is 0-100.
    rate = (present / total) if total else 0.0
    return rate >= (float(program.completion_rule_value) / 100)


async def _issue_student_certificate(
    db: AsyncSession, registration: Registration, contact: Contact, cohort: Cohort, program: Program, actor_user_id: UUID,
) -> Certificate:
    """Idempotent — returns the existing certificate if one was already
    issued (auto on complete_cohort, or by manual override) rather than
    creating a duplicate.

    Student completion certs are generated from the template and emailed
    directly as a PDF attachment — they are NOT uploaded to storage. The DB
    row records the fact of issuance (id, contact_id, registration_id, type,
    generated_at, generated_by) but carries no file_url/bucket/file_path.
    A failed email send is logged and silently swallowed — cohort completion
    must never fail because SMTP is down.

    Rendered from the `student_completion` system template (2026-08-01) — an
    editable `document_templates` row, same as `workshop_delivery` — rather
    than a hardcoded string, so admins can change the wording without a code
    change. `is_system=True` + empty `roles` keeps it out of the self-service
    "request a document" picker: nobody requests this, the system issues it.
    """
    existing = await db.scalar(select(Certificate).where(Certificate.registration_id == registration.id))
    if existing is not None:
        return existing

    dates = format_cohort_dates(cohort)
    # One-line venue snapshot on the stored certificate — resolved through
    # the canonical resolver (cohort-only, tickets/certs have no session) so
    # the printed line matches every other surface.
    location = await resolve_session_location_display(db, None, cohort)
    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == "student_completion")
    )).scalars().first()
    body_text = (template.body_text if template else "For successfully completing<br/>{program_name}<br/>{dates}") \
        .replace("{program_name}", escape(program.name)) \
        .replace("{dates}", escape(dates))
    cert_bytes = await asyncio.to_thread(generate_completion_certificate_pdf, contact.full_name, body_text)

    certificate = Certificate(
        id=uuid4(), contact_id=contact.id, registration_id=registration.id,
        type=CertificateType.student_completion,
        workshop_name=program.name, workshop_date=dates, location=location["name"],
        generated_by=actor_user_id,
    )
    db.add(certificate)
    await db.flush()

    # Email the cert as a PDF attachment — best-effort, never blocks completion.
    if contact.email:
        filename = f"SpacePoint_Certificate_{program.name.replace(' ', '_')}.pdf"
        await try_send_email(
            contact.email,
            f"Your SpacePoint certificate — {program.name}",
            _cert_email_body(contact.full_name, program.name, dates),
            html=True,
            attachments=[(filename, cert_bytes, "pdf")],
        )

    return certificate


async def complete_cohort(db: AsyncSession, cohort_id: UUID, actor_user_id: UUID) -> Cohort:
    """Ops/admin only (enforced by the router dependency, not here — unlike
    the instructor actions above, there's no per-user assignment concept for
    a whole cohort). Per registration: meets the program's completion rule
    -> status=completed + certificate issued; else status=attended (an ops
    can still manually issue one later — see issue_certificate_override).
    Then the cohort itself flips to completed. S5-2's zero-reports warning
    is layered on top of this by the router, not here."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    program = await db.get(Program, cohort.program_id)

    registrations = (await db.execute(
        select(Registration).where(Registration.cohort_id == cohort_id, Registration.status != "cancelled")
    )).scalars().all()
    for registration in registrations:
        total = await _sessions_covered(db, cohort_id, registration.id)
        present = await _present_count(db, registration.id)
        if _meets_completion_rule(program, present, total):
            registration.status = "completed"
            contact = await db.get(Contact, registration.contact_id)
            await _issue_student_certificate(db, registration, contact, cohort, program, actor_user_id)
        else:
            registration.status = "attended"

    cohort.status = "completed"
    await db.flush()
    return cohort


async def issue_certificate_override(db: AsyncSession, registration_id: UUID, actor_user_id: UUID) -> Certificate:
    """Ops/admin manual override (operator request 2026-07-25): a student
    who didn't meet the program's completion rule can still be given a
    certificate by hand — it's just not auto-issued. Marks the registration
    completed too, since the certificate is what "completed" means here.
    Idempotent — reuses _issue_student_certificate's existing-cert check, so
    calling this on an already-certified registration just returns it."""
    registration = await db.get(Registration, registration_id)
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Registration not found")
    cohort = await db.get(Cohort, registration.cohort_id)
    program = await db.get(Program, cohort.program_id)
    contact = await db.get(Contact, registration.contact_id)

    certificate = await _issue_student_certificate(db, registration, contact, cohort, program, actor_user_id)
    registration.status = "completed"
    await db.flush()
    return certificate


def _cert_email_body(student_name: str, program_name: str, dates: str) -> str:
    return (
        f"<p>Hi {student_name},</p>"
        f"<p>Congratulations on completing <strong>{program_name}</strong> ({dates})!</p>"
        "<p>Your certificate of completion is attached to this email as a PDF.</p>"
        "<p>— SpacePoint</p>"
    )
