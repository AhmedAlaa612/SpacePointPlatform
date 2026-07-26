"""Cohorts CRUD + the operations "registration desk" (V2 R2-3): session
generation, the registrations list, manual (desk) registration, per-session
instructor assignment, and the resend-ticket/cancel/confirm-payment actions.
Every route is gated by require_operations (admin passes automatically — see
core/dependencies.py's RequireRole).

Reuses the existing services rather than reimplementing them:
register()/issue_ticket() from services/sessions/registration.py, and
resolve_or_create_contact() from services/spine/identity.py. The manual
registration flow below is a deliberate near-duplicate of
routers/sessions/public.py's public_register (same resolve-contact +
guardian-relationship + register() + enqueue-ticket-email shape) — public.py
itself must not be edited, so `_ensure_guardian_relationship` is copied
here verbatim rather than imported from a "private" function in another
router module.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.dependencies import require_operations, require_session_delivery
from app.db.session import get_db
from app.models.certificate import Certificate
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session, SessionInstructor
from app.models.spine.contact import Contact, ContactRelationship
from app.models.spine.organization import Organization
from app.models.user import User
from app.schemas.sessions.cohorts import (
    AddSessionRequest,
    AssignInstructorRequest,
    CohortCreate,
    CohortOut,
    CohortUpdate,
    CompleteCohortResponse,
    GenerateSessionsRequest,
    GenerateSessionsResponse,
    SessionInstructorOut,
    SessionOut,
    UpdateSessionRequest,
)
from app.schemas.sessions.registration_desk import (
    ConfirmPaymentRequest,
    DeskRegistrationRequest,
    RegistrationAttendanceOut,
    RegistrationOut,
)
from app.schemas.sessions.reports import SessionReportOut
from app.services import storage
from app.services.notification import create_notification
from app.services.sessions import delivery
from app.services.sessions import reports as reports_service
from app.services.sessions.registration import register
from app.services.spine.identity import resolve_or_create_contact
from app.workers.settings import get_arq_redis, safe_enqueue

router = APIRouter(prefix="/sessions", tags=["sessions-cohorts"])


# ── Cohorts CRUD ─────────────────────────────────────────────────────────────

@router.get("/cohorts", response_model=list[CohortOut])
async def list_cohorts(
    program_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    stmt = select(Cohort, Program.name, Program.code).join(Program, Program.id == Cohort.program_id)
    if program_id is not None:
        stmt = stmt.where(Cohort.program_id == program_id)
    stmt = stmt.order_by(Cohort.created_at.desc())

    rows = (await db.execute(stmt)).all()
    result = []
    for cohort, program_name, program_code in rows:
        out = CohortOut.model_validate(cohort)
        out.program_name = program_name
        out.program_code = program_code
        result.append(out)
    return result


@router.post("/cohorts", response_model=CohortOut, status_code=status.HTTP_201_CREATED)
async def create_cohort(
    body: CohortCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, body.program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    cohort = Cohort(id=uuid.uuid4(), **body.model_dump())
    db.add(cohort)
    await db.commit()
    await db.refresh(cohort)
    return cohort


@router.get("/cohorts/{cohort_id}", response_model=CohortOut)
async def get_cohort(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    return cohort


@router.patch("/cohorts/{cohort_id}", response_model=CohortOut)
async def update_cohort(
    cohort_id: uuid.UUID,
    body: CohortUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Covers open/close registration too — just set `status` (planned|
    registration_open|running|completed|cancelled)."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(cohort, field, value)
    await db.commit()
    await db.refresh(cohort)
    return cohort


@router.post("/cohorts/{cohort_id}/complete", response_model=CompleteCohortResponse)
async def complete_cohort(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Ops/admin only (W5 S5-1). S5-2 adds the zero-reports warning below —
    it never blocks completion, just rides along in the response; S5-3 will
    add the attendance-rate/certificate logic on top of this same function."""
    warnings: list[str] = []
    if await reports_service.report_count_for_cohort(db, cohort_id) == 0:
        warnings.append("No session reports were uploaded for this cohort.")
    cohort = await delivery.complete_cohort(db, cohort_id, current_user.id)
    await db.commit()
    return CompleteCohortResponse(cohort=cohort, warnings=warnings)


# ── Sessions ─────────────────────────────────────────────────────────────────

async def _session_out(db: AsyncSession, session: Session) -> SessionOut:
    rows = (await db.execute(
        select(SessionInstructor, User.full_name)
        .join(User, User.id == SessionInstructor.user_id)
        .where(SessionInstructor.session_id == session.id)
    )).all()
    interest_count = (await db.execute(
        select(func.count())
        .select_from(InstructorInterest)
        .where(InstructorInterest.session_id == session.id)
    )).scalar_one()

    out = SessionOut.model_validate(session)
    out.instructors = [
        SessionInstructorOut(user_id=si.user_id, full_name=name, role=si.role) for si, name in rows
    ]
    out.interested_count = interest_count
    return out


@router.post("/cohorts/{cohort_id}/sessions:generate", response_model=GenerateSessionsResponse)
async def generate_sessions(
    cohort_id: uuid.UUID,
    body: GenerateSessionsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    if cohort.starts_on is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cohort has no starts_on date to generate sessions from")
    if not body.weekdays:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="weekdays must have at least one entry")
    if any(not (0 <= w <= 6) for w in body.weekdays):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="each weekday must be between 0 (Monday) and 6 (Sunday)")
    if body.count < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="count must be at least 1")

    created: list[Session] = []
    skipped = 0
    for weekday in body.weekdays:
        # First occurrence of this weekday on/after cohort.starts_on.
        days_ahead = (weekday - cohort.starts_on.weekday()) % 7
        first_date: date = cohort.starts_on + timedelta(days=days_ahead)

        for i in range(body.count):
            meeting_date = first_date + timedelta(weeks=i)
            existing = await db.scalar(
                select(Session.id).where(
                    Session.cohort_id == cohort_id,
                    Session.meeting_date == meeting_date,
                    Session.starts_at == body.starts_at,
                )
            )
            if existing is not None:
                skipped += 1
                continue

            session = Session(
                id=uuid.uuid4(), cohort_id=cohort_id, meeting_date=meeting_date, starts_at=body.starts_at,
            )
            db.add(session)
            try:
                async with db.begin_nested():
                    await db.flush()
            except IntegrityError:
                # Belt-and-braces against the uq_session_slot constraint —
                # the SELECT above already covers the common case.
                skipped += 1
                continue
            created.append(session)

    await db.commit()
    return GenerateSessionsResponse(
        created=[await _session_out(db, s) for s in created], skipped=skipped,
    )


@router.get("/cohorts/{cohort_id}/sessions", response_model=list[SessionOut])
async def list_sessions(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    result = await db.execute(
        select(Session)
        .where(Session.cohort_id == cohort_id)
        .order_by(Session.meeting_date, Session.starts_at)
    )
    return [await _session_out(db, s) for s in result.scalars().all()]


@router.post("/cohorts/{cohort_id}/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def add_session(
    cohort_id: uuid.UUID,
    body: AddSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """A single one-off session date — for schedules that don't fit the
    weekly generator above (an irregular extra session, a make-up date)."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    session = Session(
        id=uuid.uuid4(), cohort_id=cohort_id, meeting_date=body.meeting_date,
        starts_at=body.starts_at, title=body.title, material_url=body.material_url, price=body.price,
    )
    db.add(session)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A session already exists at this date and time")
    await db.commit()
    await db.refresh(session)
    return await _session_out(db, session)


@router.patch("/cohorts/{cohort_id}/sessions/{session_id}", response_model=SessionOut)
async def update_session(
    cohort_id: uuid.UUID,
    session_id: uuid.UUID,
    body: UpdateSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    session = await db.get(Session, session_id)
    if session is None or session.cohort_id != cohort_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(session, field, value)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A session already exists at this date and time")
    await db.commit()
    await db.refresh(session)
    return await _session_out(db, session)


# ── Per-session instructor assignment ───────────────────────────────────────

@router.post(
    "/cohorts/{cohort_id}/sessions/{session_id}/instructors",
    response_model=SessionInstructorOut, status_code=status.HTTP_201_CREATED,
)
async def assign_instructor(
    cohort_id: uuid.UUID,
    session_id: uuid.UUID,
    body: AssignInstructorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    session = await db.get(Session, session_id)
    if session is None or session.cohort_id != cohort_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    user = await db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")

    existing = await db.scalar(
        select(SessionInstructor).where(
            SessionInstructor.session_id == session_id, SessionInstructor.user_id == body.user_id,
        )
    )
    if existing is not None:
        existing.role = body.role
    else:
        db.add(SessionInstructor(id=uuid.uuid4(), session_id=session_id, user_id=body.user_id, role=body.role))
    # Direct assign bypasses the open-call/interest marketplace entirely
    # (W4) — but the session is genuinely staffed either way, so keep
    # staffing_status honest regardless of which path got it there.
    session.staffing_status = "staffed"
    await db.commit()
    return SessionInstructorOut(user_id=user.id, full_name=user.full_name, role=body.role)


@router.delete("/cohorts/{cohort_id}/sessions/{session_id}/instructors/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_instructor(
    cohort_id: uuid.UUID,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    session = await db.get(Session, session_id)
    if session is None or session.cohort_id != cohort_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    assignment = await db.scalar(
        select(SessionInstructor).where(
            SessionInstructor.session_id == session_id, SessionInstructor.user_id == user_id,
        )
    )
    if assignment is not None:
        await db.delete(assignment)
        await db.flush()
        remaining = await db.scalar(
            select(func.count()).select_from(SessionInstructor).where(SessionInstructor.session_id == session_id)
        )
        # Only auto-revert a direct assignment's implicit "staffed" — never
        # touches open_call (that's the marketplace's own explicit reopen()).
        if remaining == 0 and session.staffing_status == "staffed":
            session.staffing_status = "unstaffed"
        # S4-2 spec: "on removal -> notify" (in-app only, no email — unlike
        # selection, being taken off a session isn't a calendar event).
        await create_notification(
            db, user_id, "Removed from a session",
            body=f"You've been removed from the session on {session.meeting_date}.",
            type="staffing_removed",
        )
        await db.commit()


# ── Session reports (W5 S5-2) ────────────────────────────────────────────────

@router.post("/cohorts/{cohort_id}/reports", response_model=SessionReportOut, status_code=status.HTTP_201_CREATED)
async def upload_session_report(
    cohort_id: uuid.UUID,
    file: UploadFile = File(...),
    session_id: uuid.UUID | None = Form(None),
    notes: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Assigned instructor (if session_id given) or ops/admin. A cohort-level
    report (no session_id) is ops/admin only — there's no per-user
    assignment concept above the session level."""
    data = await file.read()
    report = await reports_service.upload_report(
        db, cohort_id, session_id, data, file.filename or "report",
        file.content_type or "application/octet-stream", notes, current_user,
    )
    await db.commit()
    file_url = await reports_service.resolve_report_url(report)
    return SessionReportOut(
        id=report.id, cohort_id=report.cohort_id, session_id=report.session_id,
        uploaded_by=report.uploaded_by, uploaded_by_name=current_user.full_name,
        file_url=file_url, filename=reports_service.display_filename(report.file_ref),
        notes=report.notes, created_at=report.created_at,
    )


@router.get("/cohorts/{cohort_id}/reports", response_model=list[SessionReportOut])
async def list_cohort_reports(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    rows = await reports_service.list_reports(db, cohort_id)
    return [
        SessionReportOut(
            id=report.id, cohort_id=report.cohort_id, session_id=report.session_id,
            uploaded_by=report.uploaded_by, uploaded_by_name=uploader_name,
            file_url=await reports_service.resolve_report_url(report),
            filename=reports_service.display_filename(report.file_ref),
            notes=report.notes, created_at=report.created_at,
        )
        for report, uploader_name in rows
    ]


# ── Registrations ────────────────────────────────────────────────────────────

@router.get("/cohorts/{cohort_id}/registrations", response_model=list[RegistrationOut])
async def list_registrations(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    Student = aliased(Contact)
    Guardian = aliased(Contact)
    StudentOrg = aliased(Organization)

    rows = (await db.execute(
        select(Registration, Student, Guardian, StudentOrg)
        .join(Student, Student.id == Registration.contact_id)
        .outerjoin(Guardian, Guardian.id == Registration.payer_contact_id)
        .outerjoin(StudentOrg, StudentOrg.id == Student.organization_id)
        .where(Registration.cohort_id == cohort_id)
        .order_by(Registration.created_at.desc())
    )).all()

    cohort_sessions = (await db.execute(
        select(Session)
        .where(Session.cohort_id == cohort_id)
        .order_by(Session.meeting_date, Session.starts_at)
    )).scalars().all()
    total_sessions_count = len(cohort_sessions)

    registration_ids = [reg.id for reg, _, _, _ in rows]
    checked_in_ids: set[uuid.UUID] = set()
    certificate_urls: dict[uuid.UUID, str] = {}
    att_by_reg: dict[uuid.UUID, dict[uuid.UUID, AttendanceRecord]] = {}

    if registration_ids:
        att_records = (await db.execute(
            select(AttendanceRecord)
            .where(AttendanceRecord.registration_id.in_(registration_ids))
        )).scalars().all()

        for rec in att_records:
            checked_in_ids.add(rec.registration_id)
            if rec.registration_id not in att_by_reg:
                att_by_reg[rec.registration_id] = {}
            att_by_reg[rec.registration_id][rec.session_id] = rec

        certs = (await db.execute(
            select(Certificate).where(Certificate.registration_id.in_(registration_ids))
        )).scalars().all()
        for cert in certs:
            # resolve_url already prefers a fresh signed URL from (bucket, path)
            # and falls back to a stored file_url — guarding on bucket/path here
            # defeated that fallback, hiding the URL on any row that only has
            # file_url. Student completion certs have neither (emailed, never
            # stored), so they correctly stay None.
            url = await storage.resolve_url(cert.bucket, cert.file_path, cert.file_url)
            if url:
                certificate_urls[cert.registration_id] = url

    result_registrations = []
    for reg, student, guardian, student_org in rows:
        reg_att_dict = att_by_reg.get(reg.id, {})
        att_list = []
        attended_count = 0
        for s in cohort_sessions:
            rec = reg_att_dict.get(s.id)
            status_val = rec.att_status if rec else "unrecorded"
            if status_val in ("present", "late"):
                attended_count += 1
            att_list.append(
                RegistrationAttendanceOut(
                    session_id=s.id,
                    meeting_date=s.meeting_date,
                    session_title=s.title,
                    att_status=status_val,
                    recorded_at=rec.recorded_at if rec else None,
                )
            )

        result_registrations.append(
            RegistrationOut(
                id=reg.id,
                contact_id=reg.contact_id,
                student_name=student.full_name,
                student_phone=student.primary_phone_e164,
                student_email=student.email,
                student_date_of_birth=student.date_of_birth,
                student_grade=student.grade,
                student_organization_name=student_org.name_latin if student_org is not None else None,
                payer_contact_id=reg.payer_contact_id,
                guardian_name=guardian.full_name if guardian is not None else None,
                guardian_phone=guardian.primary_phone_e164 if guardian is not None else None,
                payment_status=reg.payment_status,
                price_charged=reg.price_charged,
                status=reg.status,
                registered_via=reg.registered_via,
                is_repeat=reg.is_repeat,
                ticket_sent=reg.ticket_sent_at is not None,
                checked_in=reg.id in checked_in_ids,
                certificate_url=certificate_urls.get(reg.id),
                attended_sessions_count=attended_count,
                total_cohort_sessions_count=total_sessions_count,
                attendance_records=att_list,
                created_at=reg.created_at,
            )
        )
    return result_registrations


# ── Manual (desk) registration ───────────────────────────────────────────────

@router.post("/cohorts/{cohort_id}/registrations", status_code=status.HTTP_201_CREATED)
async def desk_register(
    cohort_id: uuid.UUID,
    body: DeskRegistrationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    student, _ = await resolve_or_create_contact(
        db,
        full_name=body.student_name,
        phone=body.phone,
        email=body.email,
        contact_roles=["student"],
        city=body.city,
        role_event_source="desk",
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
            role_event_source="desk",
        )
        payer_contact_id = guardian.id
        await _ensure_guardian_relationship(db, student_id=student.id, guardian_id=guardian.id)

    registration = await register(
        db,
        contact_id=student.id,
        cohort_id=cohort.id,
        payer_contact_id=payer_contact_id,
        registered_via="desk",
        session_ids=body.session_ids,
    )

    await db.commit()

    # Ticket email runs on the ARQ queue, not synchronously — same pattern as
    # the public registration endpoint (routers/sessions/public.py). Desk
    # staff can opt out entirely (e.g. printing the ticket directly instead).
    if body.send_ticket_email:
        await safe_enqueue(arq_redis, "send_ticket_email", str(registration.id))

    return {
        "id": str(registration.id),
        "contact_id": str(student.id),
        "payer_contact_id": str(payer_contact_id) if payer_contact_id else None,
        "status": registration.status,
    }


async def _ensure_guardian_relationship(db: AsyncSession, *, student_id: uuid.UUID, guardian_id: uuid.UUID) -> None:
    """Copied verbatim from routers/sessions/public.py — see that module for
    the canonical version; do not let this drift from it."""
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


# ── Registration actions ─────────────────────────────────────────────────────

@router.post("/registrations/{registration_id}/resend-ticket")
async def resend_ticket(
    registration_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    registration = await db.get(Registration, registration_id)
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Registration not found")

    # force=True: this is the one path where re-sending an already-sent ticket
    # is the intent, so it deliberately bypasses issue_ticket's idempotency guard.
    status_ = await safe_enqueue(
        arq_redis, "send_ticket_email", str(registration.id), force=True
    )
    return {"status": status_}


@router.post("/registrations/{registration_id}/cancel")
async def cancel_registration(
    registration_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    registration = await db.get(Registration, registration_id)
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Registration not found")

    registration.status = "cancelled"
    await db.commit()
    return {"id": str(registration.id), "status": registration.status}


@router.post("/registrations/{registration_id}/certificate")
async def give_certificate(
    registration_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Manual override (operator request 2026-07-25): ops can hand a
    certificate to a student who didn't meet the program's completion rule
    — it's just never auto-sent for them. Idempotent, same as the automatic
    path in complete_cohort."""
    certificate = await delivery.issue_certificate_override(db, registration_id, current_user.id)
    await db.commit()
    # Student completion certs are emailed directly — no file stored, no URL to return.
    return {"id": str(registration_id), "status": "completed", "certificate_id": str(certificate.id)}



@router.post("/registrations/{registration_id}/confirm-payment")
async def confirm_payment(
    registration_id: uuid.UUID,
    body: ConfirmPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    registration = await db.get(Registration, registration_id)
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Registration not found")

    registration.price_charged = body.amount
    registration.payment_status = body.status
    await db.commit()
    return {
        "id": str(registration.id),
        "payment_status": registration.payment_status,
        "price_charged": str(registration.price_charged),
    }
