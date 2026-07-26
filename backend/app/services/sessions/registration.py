"""Registration service (V2 R1-4).

register() is the commercial record — the ticket IS the registration row,
there is no separate tickets table (see MASTER_EXECUTION_PLAN_V2.md R1-2).
issue_ticket() renders the QR and sends the email; check_in() resolves a
scanned/typed token back to a registration and records attendance.

Follows this codebase's existing convention (see services/interns/epic.py,
proposal.py) of raising HTTPException directly from the service layer rather
than a separate domain-exception-translation layer.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spine.contact import Contact
from app.models.spine.touchpoint import Touchpoint
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration, RegistrationSession
from app.models.sessions.session import Session
from app.services.documents.ticket import ticket_url
from app.services.documents.ticket_image import render_ticket_png
from app.services.email import try_send_email

logger = logging.getLogger(__name__)

# A registration counts against cohort capacity unless cancelled.
ACTIVE_REGISTRATION_STATUSES = ("registered", "attended", "completed")

# registered_via -> touchpoint channel. 'form' is the public web form; 'import'
# is a bulk sheet upload (no human channel, hence 'system'); 'desk' is an ops
# staff member registering someone in person/by phone.
_CHANNEL_BY_REGISTERED_VIA = {"form": "web", "import": "system", "desk": "offline"}


async def register(
    db: AsyncSession,
    *,
    contact_id: UUID,
    cohort_id: UUID,
    registered_via: Literal["form", "import", "desk"],
    payer_contact_id: UUID | None = None,
    price_charged: float | None = None,
    source_touchpoint_id: UUID | None = None,
    payment_status: Literal["unpaid", "partial", "paid", "waived", "refunded"] | None = None,
    session_ids: list[UUID] | None = None,
) -> Registration:
    """Create a registration. Raises HTTPException (409) if the cohort is
    full, (409) if this contact is already registered for this cohort.

    `session_ids`, if given, restricts this registration to specific sessions
    within the cohort (a student attending only some of a multi-session
    program). Leave it None to cover every session in the cohort — the
    common case for a single-session workshop, and also correct if this
    registration happens before every session has been generated yet."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    if cohort.capacity is not None:
        active_count = await db.scalar(
            select(func.count())
            .select_from(Registration)
            .where(Registration.cohort_id == cohort_id, Registration.status.in_(ACTIVE_REGISTRATION_STATUSES))
        )
        if active_count >= cohort.capacity:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This cohort is full")

    contact = await db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Contact not found")

    is_repeat = bool(
        await db.scalar(
            select(Registration.id)
            .where(Registration.contact_id == contact_id, Registration.status == "completed")
            .limit(1)
        )
    )

    if payment_status is None:
        program = await db.get(Program, cohort.program_id)
        payment_status = "waived" if program is not None and program.pricing_model == "free" else "unpaid"

    # A cancelled registration still occupies the UNIQUE(contact_id, cohort_id)
    # slot, so re-registering someone who dropped out used to fail with "already
    # registered" — and nothing could move a row out of `cancelled`, making the
    # cancel button a one-way trap. Reinstate the existing row instead: the
    # student keeps their original created_at, touchpoint history and ticket
    # token, and clearing ticket_sent_at lets the caller send it to them again.
    # An *active* duplicate still 409s below, exactly as before.
    existing = (await db.execute(
        select(Registration).where(
            Registration.contact_id == contact_id, Registration.cohort_id == cohort_id,
        )
    )).scalars().first()
    if existing is not None and existing.status == "cancelled":
        existing.status = "registered"
        existing.ticket_sent_at = None
        existing.registered_via = registered_via
        if payment_status is not None:
            existing.payment_status = payment_status
        await db.flush()
        if session_ids:
            # Replace any coverage from the previous life of this row rather
            # than adding to it — the caller is stating the full set.
            await db.execute(
                sa_delete(RegistrationSession).where(RegistrationSession.registration_id == existing.id)
            )
            for session_id in session_ids:
                db.add(RegistrationSession(id=uuid4(), registration_id=existing.id, session_id=session_id))
        db.add(Touchpoint(
            contact_id=contact_id,
            channel=_CHANNEL_BY_REGISTERED_VIA[registered_via],
            touchpoint_type="registration",
            occurred_at=datetime.now(timezone.utc),
            raw_platform_id=f"registration:{existing.id}:reinstated:{uuid4()}",
        ))
        await db.flush()
        return existing

    registration = Registration(
        id=uuid4(),
        contact_id=contact_id,
        payer_contact_id=payer_contact_id,
        cohort_id=cohort_id,
        price_charged=price_charged,
        payment_status=payment_status,
        status="registered",
        source_touchpoint_id=source_touchpoint_id,
        is_repeat=is_repeat,
        ticket_token=secrets.token_urlsafe(32),
        registered_via=registered_via,
    )
    db.add(registration)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, detail="This contact is already registered for this cohort"
        ) from exc

    db.add(Touchpoint(
        contact_id=contact_id,
        channel=_CHANNEL_BY_REGISTERED_VIA[registered_via],
        touchpoint_type="registration",
        occurred_at=datetime.now(timezone.utc),
        raw_platform_id=f"registration:{registration.id}",
    ))

    if session_ids:
        for session_id in session_ids:
            db.add(RegistrationSession(id=uuid4(), registration_id=registration.id, session_id=session_id))

    await db.flush()
    return registration


async def issue_ticket(db: AsyncSession, registration_id: UUID, force: bool = False) -> bool:
    """Render the QR and email the ticket. Returns False (logged, not raised —
    a failed send must never break registration) if there's no email to send
    to, or if SMTP itself fails. Sets ticket_sent_at only on success.

    Idempotent on `ticket_sent_at`: a registration whose ticket already went
    out is a no-op returning True, so a job delivered more than once (ARQ
    retry, a duplicate enqueue, a re-run import batch) can't mail the same
    student twice. `force=True` is the deliberate override behind the ops
    resend-ticket action — the one case where a second send is the point.
    """
    registration = await db.get(Registration, registration_id)
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Registration not found")

    if registration.ticket_sent_at is not None and not force:
        logger.info(
            "Ticket for registration %s already sent at %s — skipping duplicate send",
            registration_id, registration.ticket_sent_at,
        )
        return True

    contact = await db.get(Contact, registration.contact_id)
    cohort = await db.get(Cohort, registration.cohort_id)
    program = await db.get(Program, cohort.program_id) if cohort else None

    if contact is None or not contact.email:
        return False

    dates = format_cohort_dates(cohort)

    ticket_png = render_ticket_png(
        student_name=contact.full_name,
        program_name=program.name if program else "your workshop",
        dates=dates,
        location=cohort.location if cohort else None,
        ticket_token=registration.ticket_token,
    )

    sent = await try_send_email(
        contact.email,
        f"Your SpacePoint ticket — {program.name if program else 'Workshop'}",
        _ticket_email_body(
            student_name=contact.full_name,
            program_name=program.name if program else "your workshop",
            dates=dates,
            location=cohort.location if cohort else None,
            ticket_link=ticket_url(registration.ticket_token),
        ),
        html=True,
        inline_images={"ticket": (ticket_png, "image", "png")},
    )
    if sent:
        registration.ticket_sent_at = datetime.now(timezone.utc)
        await db.flush()
    return sent


async def check_in(db: AsyncSession, token: str, session_id: UUID, actor_user_id: UUID | None) -> AttendanceRecord:
    """Resolve a scanned/typed ticket token and record attendance for one
    session. 404 if the token doesn't resolve to any registration, 409 if the
    session belongs to a different cohort than the one this ticket is for,
    409 if this registration was restricted to specific sessions and this
    isn't one of them, 409 if attendance was already recorded for this
    session."""
    registration = await db.scalar(select(Registration).where(Registration.ticket_token == token))
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Unknown ticket")

    session = await db.get(Session, session_id)
    if session is None or session.cohort_id != registration.cohort_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This ticket is not for this session")

    # An empty registration_sessions set means "covers every session in the
    # cohort" (see register()'s session_ids doc) — only enforce coverage when
    # this registration was explicitly restricted to a subset.
    covered_session_ids = (await db.scalars(
        select(RegistrationSession.session_id).where(RegistrationSession.registration_id == registration.id)
    )).all()
    if covered_session_ids and session_id not in covered_session_ids:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This ticket isn't registered for this session")

    existing = await db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.registration_id == registration.id,
            AttendanceRecord.session_id == session_id,
        )
    )
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Attendance already recorded for this session")

    record = AttendanceRecord(
        id=uuid4(),
        registration_id=registration.id,
        session_id=session_id,
        att_status="present",
        method="qr",
        recorded_by_user_id=actor_user_id,
    )
    db.add(record)
    await db.flush()
    return record


def format_cohort_dates(cohort: Cohort | None) -> str:
    if cohort is None or not cohort.starts_on:
        return "Date to be confirmed"
    if cohort.ends_on and cohort.ends_on != cohort.starts_on:
        return f"{cohort.starts_on:%b %d, %Y} – {cohort.ends_on:%b %d, %Y}"
    return f"{cohort.starts_on:%b %d, %Y}"


def _ticket_email_body(*, student_name: str, program_name: str, dates: str, location: str | None, ticket_link: str) -> str:
    return (
        f"<p>Hi {student_name},</p>"
        f"<p>You're registered for <strong>{program_name}</strong>.</p>"
        f"<p><strong>When:</strong> {dates}<br>"
        f"<strong>Where:</strong> {location or 'To be confirmed'}</p>"
        f'<p style="text-align:center"><img src="cid:ticket" alt="Your Ticket" style="display:block;max-width:525px;height:auto;margin:20px auto;border-radius:18px"></p>'
        f"<p>Show this ticket at the door. You can also view it online: "
        f'<a href="{ticket_link}">{ticket_link}</a></p>'
        "<p>— SpacePoint</p>"
    )
