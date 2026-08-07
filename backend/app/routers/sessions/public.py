"""Public registration endpoint (V2 R1-5) — no auth, rate-limited, honeypot-
guarded. Mounted at /public/register/{cohort_key} — this codebase has no
/api prefix anywhere (VERIFY against main.py: every router mounts at root),
unlike the literal path in MASTER_EXECUTION_PLAN_V2.md; followed the real
convention instead, matching the existing /public/* pattern in
routers/ambassadors/public.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from arq.connections import ArqRedis

from app.db.session import get_db
from app.core.rate_limit import enforce_rate_limit
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_interest import CohortInterest
from app.models.lms.curriculum import ProgramCurriculum
from app.models.lms.course import Course
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session, SessionInstructor
from app.models.spine.contact import Contact, ContactRelationship
from app.models.user import User
from app.schemas.sessions.catalog import CatalogCohortOut, CatalogSessionOut, PublicTicketOut
from app.schemas.sessions.public_registration import PublicInterestRequest, PublicRegistrationRequest
from app.services.documents.ticket import generate_ticket_qr_png
from app.services.spine.identity import resolve_or_create_contact
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES, format_cohort_dates, register
from app.workers.settings import get_arq_redis, safe_enqueue

router = APIRouter(prefix="/public", tags=["public-registration"])

_OPEN_STATUSES = ("planned", "registration_open")


@router.get("/catalog", response_model=list[CatalogCohortOut])
async def public_catalog(db: AsyncSession = Depends(get_db)):
    """Public cohorts a marketing site (or the LMS's own "Upcoming programs")
    can list (V2 R3-1, extended 2026-08-07 for the planned/registration_open
    dual CTA). No auth, no rate limit — read-only and cheap; the abuse-prone
    endpoints are the two POSTs below, not this GET.

    `planned` cohorts are included now (not just `registration_open`) so a
    student can see what's coming and register interest before it opens —
    the operator's own framing: "planned = register interest, registration
    open = register now."
    """
    rows = (await db.execute(
        select(Cohort, Program)
        .join(Program, Program.id == Cohort.program_id)
        .where(Cohort.status.in_(_OPEN_STATUSES), Cohort.visibility == "public")
        .order_by(Cohort.starts_on.asc().nullslast())
    )).all()

    cohort_ids = [cohort.id for cohort, _ in rows]
    program_ids = {program.id for _, program in rows}

    active_counts: dict[uuid.UUID, int] = {}
    sessions_by_cohort: dict[uuid.UUID, list[Session]] = {}
    instructors_by_cohort: dict[uuid.UUID, set[str]] = {}
    curriculum_by_program: dict[uuid.UUID, list[str]] = {}

    if cohort_ids:
        count_rows = (await db.execute(
            select(Registration.cohort_id, func.count())
            .where(
                Registration.cohort_id.in_(cohort_ids),
                Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
            )
            .group_by(Registration.cohort_id)
        )).all()
        active_counts = dict(count_rows)

        session_rows = (await db.execute(
            select(Session)
            .where(Session.cohort_id.in_(cohort_ids))
            .order_by(Session.meeting_date.asc(), Session.starts_at.asc().nullslast())
        )).scalars().all()
        for s in session_rows:
            sessions_by_cohort.setdefault(s.cohort_id, []).append(s)

        session_ids = [s.id for s in session_rows]
        if session_ids:
            instructor_rows = (await db.execute(
                select(Session.cohort_id, User.full_name)
                .select_from(SessionInstructor)
                .join(Session, Session.id == SessionInstructor.session_id)
                .join(User, User.id == SessionInstructor.user_id)
                .where(SessionInstructor.session_id.in_(session_ids))
            )).all()
            for cohort_id, full_name in instructor_rows:
                instructors_by_cohort.setdefault(cohort_id, set()).add(full_name)

    if program_ids:
        curriculum_rows = (await db.execute(
            select(ProgramCurriculum.program_id, Course.title)
            .join(Course, Course.id == ProgramCurriculum.course_id)
            .where(ProgramCurriculum.program_id.in_(program_ids))
            .order_by(ProgramCurriculum.position)
        )).all()
        for program_id, title in curriculum_rows:
            curriculum_by_program.setdefault(program_id, []).append(title)

    items: list[CatalogCohortOut] = []
    for cohort, program in rows:
        spots_left = None
        is_limited = False
        if cohort.capacity is not None:
            spots_left = max(cohort.capacity - active_counts.get(cohort.id, 0), 0)
            is_limited = cohort.capacity > 0 and (spots_left / cohort.capacity) < 0.10

        if program.pricing_model == "free":
            price_display = "Free"
        elif program.price is not None:
            price_display = f"AED {program.price}"
        else:
            price_display = "Paid"

        items.append(CatalogCohortOut(
            cohort_id=cohort.id,
            program_name=program.name,
            program_type=program.program_type,
            description=program.description,
            starts_on=cohort.starts_on,
            ends_on=cohort.ends_on,
            location=cohort.location,
            price_display=price_display,
            capacity=cohort.capacity,
            spots_left=spots_left,
            is_limited=is_limited,
            registration_endpoint=f"/public/register/{cohort.id}",
            status=cohort.status,
            interest_endpoint=f"/public/interest/{cohort.id}",
            sessions=[
                CatalogSessionOut(meeting_date=s.meeting_date, starts_at=s.starts_at, title=s.title)
                for s in sessions_by_cohort.get(cohort.id, [])
            ],
            instructors=sorted(instructors_by_cohort.get(cohort.id, set())),
            curriculum_titles=curriculum_by_program.get(program.id, []),
        ))

    return items


@router.post("/register/{cohort_key}", status_code=status.HTTP_201_CREATED)
async def public_register(
    cohort_key: uuid.UUID,
    body: PublicRegistrationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    # Rate-limit before the honeypot check, so a flood of bot-filled requests
    # still gets throttled even though they'll be dropped either way.
    enforce_rate_limit(request)

    if body.website:
        # Honeypot tripped — a human never sees this field. Return the same
        # success shape as a real registration so a bot can't distinguish a
        # drop from a real acceptance; just don't do anything.
        return {"message": "You're registered! Check your email for your ticket."}

    cohort = await db.get(Cohort, cohort_key)
    if cohort is None or cohort.status != "registration_open" or cohort.visibility != "public":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Registration is not open for this cohort")

    student, _ = await resolve_or_create_contact(
        db,
        full_name=body.student_name,
        phone=body.phone,
        email=body.email,
        contact_roles=["student"],
        city=body.city,
        date_of_birth=body.date_of_birth,
        grade=body.grade,
        organization_name=body.organization_name,
    )

    payer_contact_id = None
    if body.parent_name and body.parent_phone:
        guardian, _ = await resolve_or_create_contact(
            db,
            full_name=body.parent_name,
            phone=body.parent_phone,
            email=body.parent_email,
            contact_roles=["parent_guardian"],
        )
        payer_contact_id = guardian.id
        await _ensure_guardian_relationship(db, student_id=student.id, guardian_id=guardian.id)

    registration = await register(
        db,
        contact_id=student.id,
        cohort_id=cohort.id,
        payer_contact_id=payer_contact_id,
        registered_via="form",
        session_ids=body.session_ids,
    )

    await db.commit()

    # Ticket email now runs on the ARQ queue (V2 R2-1), not synchronously in
    # this request (that was R1-4's explicitly-flagged W1 interim). A failed
    # or slow send — or Redis being unreachable at all (safe_enqueue) — must
    # never hold up or undo a successful registration.
    await safe_enqueue(arq_redis, "send_ticket_email", str(registration.id))

    return {
        "message": "You're registered! Check your email for your ticket.",
        "email": _mask_email(body.email),
    }


@router.post("/interest/{cohort_key}", status_code=status.HTTP_201_CREATED)
async def public_register_interest(
    cohort_key: uuid.UUID,
    body: PublicInterestRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """"Notify me" for a `planned` cohort — same identity-resolution flow as
    real registration (so it dedupes against and shows up on the same
    contact record), but writes to `cohort_interest`, not `Registration`:
    no payment/attendance/ticket state applies to "just interested."
    """
    enforce_rate_limit(request)

    if body.website:
        return {"message": "Thanks — we'll email you when registration opens."}

    cohort = await db.get(Cohort, cohort_key)
    if cohort is None or cohort.status != "planned" or cohort.visibility != "public":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This cohort isn't taking interest signups")

    contact, _ = await resolve_or_create_contact(
        db, full_name=body.student_name, phone=body.phone, email=body.email, contact_roles=["student"],
    )

    existing = (await db.execute(
        select(CohortInterest).where(
            CohortInterest.contact_id == contact.id, CohortInterest.cohort_id == cohort.id,
        )
    )).scalars().first()
    if existing is None:
        db.add(CohortInterest(id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id))

    await db.commit()

    return {
        "message": "Thanks — we'll email you when registration opens.",
        "email": _mask_email(body.email),
    }


async def _ensure_guardian_relationship(db: AsyncSession, *, student_id: uuid.UUID, guardian_id: uuid.UUID) -> None:
    result = await db.execute(
        select(ContactRelationship).where(
            ContactRelationship.contact_id == guardian_id,
            ContactRelationship.related_contact_id == student_id,
            ContactRelationship.relation == "guardian_of",
        )
    )
    if result.scalars().first() is not None:
        return
    db.add(ContactRelationship(
        id=uuid.uuid4(), contact_id=guardian_id, related_contact_id=student_id, relation="guardian_of",
    ))
    await db.flush()


def _mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    if len(name) <= 2:
        masked = name[:1] + "***"
    else:
        masked = name[:2] + "***"
    return f"{masked}@{domain}"


@router.get("/ticket/{ticket_token}", response_model=PublicTicketOut)
async def public_ticket(ticket_token: str, db: AsyncSession = Depends(get_db)):
    """The page the emailed ticket link and the QR code both point at.

    No auth by design: the token *is* the credential, exactly as it is when a
    staff member scans the QR at the door. It's a 64-char urlsafe random, and
    the response deliberately carries nothing beyond what's already printed on
    the student's own ticket. An unknown token is a flat 404 — no hint as to
    whether it ever existed.
    """
    registration = (await db.execute(
        select(Registration).where(Registration.ticket_token == ticket_token)
    )).scalars().first()
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    contact = await db.get(Contact, registration.contact_id)
    cohort = await db.get(Cohort, registration.cohort_id)
    program = await db.get(Program, cohort.program_id) if cohort else None

    checked_in = (await db.scalar(
        select(func.count()).select_from(AttendanceRecord)
        .where(AttendanceRecord.registration_id == registration.id)
    )) or 0

    return PublicTicketOut(
        student_name=contact.full_name if contact else "—",
        program_name=program.name if program else "Workshop",
        cohort_name=cohort.name if cohort else "—",
        dates=format_cohort_dates(cohort),
        location=cohort.location if cohort else None,
        ticket_token=registration.ticket_token,
        status=registration.status,
        checked_in=bool(checked_in),
    )


@router.get("/ticket/{ticket_token}/qr.png")
async def public_ticket_qr(ticket_token: str, db: AsyncSession = Depends(get_db)):
    """The QR itself, as a PNG — same image the ticket email embeds, so the
    page and the email can't drift apart. Same no-auth reasoning as above."""
    exists = await db.scalar(
        select(func.count()).select_from(Registration)
        .where(Registration.ticket_token == ticket_token)
    )
    if not exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    return Response(
        content=generate_ticket_qr_png(ticket_token),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )
