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

import asyncio
import uuid
from datetime import date, timedelta
from html import escape

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.dependencies import require_operations, require_session_delivery
from app.db.session import get_db
from app.models.certificate import Certificate
from app.models.document_template import DocumentTemplate
from app.models.sessions.delivery_role import DeliveryRole
from app.services.documents.certificate import generate_completion_certificate_pdf, merge_certificate_pdfs
from app.services.sessions.openings import fully_staffed, lead_role_id
from app.models.inventory.location import Location
from app.models.inventory.warehouse import Warehouse
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session, SessionInstructor
from app.models.sessions.session_report import SessionReport
from app.models.inventory.item import Item
from app.models.inventory.kit import Kit
from app.models.inventory.movement import Movement
from app.models.inventory.session_kit import KitCheck, SessionKit
from app.services.sessions import openings as openings_svc
from app.models.spine.contact import Contact, ContactRelationship
from app.models.spine.organization import Organization
from app.models.user import User
from app.schemas.sessions.cohorts import (
    AddSessionRequest,
    AssignInstructorRequest,
    BulkActionError,
    BulkActionResult,
    BulkAssignInstructorRequest,
    BulkOpenCallRequest,
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
from app.services.inventory.cohort_kits import resolve_session_kits
from app.services.sessions import delivery
from app.services.sessions import materials as materials_service
from app.services.sessions import staffing as staffing_service
from app.services.sessions import reports as reports_service
from app.services.sessions.registration import format_cohort_dates, register
from app.services.spine.identity import resolve_or_create_contact
from app.workers.settings import get_arq_redis, safe_enqueue

router = APIRouter(prefix="/sessions", tags=["sessions-cohorts"])


# ── Cohorts CRUD ─────────────────────────────────────────────────────────────

async def _resolve_effective_warehouse(
    db: AsyncSession, *, warehouse_id: uuid.UUID | None, location_id: uuid.UUID | None
) -> Warehouse | None:
    """The warehouse override wins when set. Otherwise, a location with
    exactly one warehouse resolves unambiguously; a location with more than
    one (or no location at all) leaves it for ops to say."""
    if warehouse_id:
        return await db.get(Warehouse, warehouse_id)
    if location_id:
        warehouses = (await db.execute(
            select(Warehouse).where(Warehouse.location_id == location_id, Warehouse.is_active.is_(True))
        )).scalars().all()
        if len(warehouses) == 1:
            return warehouses[0]
    return None


async def _cohort_out(
    db: AsyncSession, cohort: Cohort, program_name: str | None = None, program_code: str | None = None,
    location: Location | None = None, counts: tuple[int, int, int, date | None] | None = None,
) -> CohortOut:
    out = CohortOut.model_validate(cohort)
    out.program_name = program_name
    out.program_code = program_code
    if counts is not None:
        out.sessions_count, out.registrations_count, out.unstaffed_count, out.next_session_date = counts
    if location is not None:
        out.location_name = location.name
        out.location_maps_url = location.maps_url

    warehouse = await _resolve_effective_warehouse(
        db, warehouse_id=cohort.warehouse_id, location_id=cohort.location_id
    )
    if warehouse is not None:
        out.effective_warehouse_id = warehouse.id
        out.effective_warehouse_name = warehouse.name
    return out


@router.get("/cohorts", response_model=list[CohortOut])
async def list_cohorts(
    program_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    # Correlated scalar subqueries rather than GROUP BY joins: counting
    # sessions and registrations in the same join would multiply the rows
    # against each other and inflate both. These are the numbers the cohorts
    # worklist needs to answer "what needs attention" without N+1 requests.
    sessions_count = (
        select(func.count(Session.id)).where(Session.cohort_id == Cohort.id).scalar_subquery()
    )
    unstaffed_count = (
        select(func.count(Session.id))
        .where(Session.cohort_id == Cohort.id, Session.staffing_status == "unstaffed")
        .scalar_subquery()
    )
    # Cancelled sign-ups don't hold a seat, so they don't count against capacity.
    registrations_count = (
        select(func.count(Registration.id))
        .where(Registration.cohort_id == Cohort.id, Registration.status != "cancelled")
        .scalar_subquery()
    )
    next_session_date = (
        select(func.min(Session.meeting_date))
        .where(Session.cohort_id == Cohort.id, Session.meeting_date >= date.today())
        .scalar_subquery()
    )

    stmt = (
        select(
            Cohort, Program.name, Program.code, Location,
            sessions_count, registrations_count, unstaffed_count, next_session_date,
        )
        .join(Program, Program.id == Cohort.program_id)
        .outerjoin(Location, Location.id == Cohort.location_id)
    )
    if program_id is not None:
        stmt = stmt.where(Cohort.program_id == program_id)
    stmt = stmt.order_by(Cohort.created_at.desc())

    rows = (await db.execute(stmt)).all()
    return [
        await _cohort_out(db, cohort, program_name, program_code, location, (sessions, regs, unstaffed, next_date))
        for cohort, program_name, program_code, location, sessions, regs, unstaffed, next_date in rows
    ]


@router.post("/cohorts", response_model=CohortOut, status_code=status.HTTP_201_CREATED)
async def create_cohort(
    body: CohortCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, body.program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")
    location = await db.get(Location, body.location_id) if body.location_id else None
    if body.location_id and location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Location not found")
    if body.warehouse_id and await db.get(Warehouse, body.warehouse_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")

    cohort = Cohort(id=uuid.uuid4(), **body.model_dump())
    db.add(cohort)
    await db.commit()
    await db.refresh(cohort)
    return await _cohort_out(db, cohort, program.name, program.code, location)


@router.get("/cohorts/{cohort_id}", response_model=CohortOut)
async def get_cohort(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    program = await db.get(Program, cohort.program_id)
    location = await db.get(Location, cohort.location_id) if cohort.location_id else None
    return await _cohort_out(db, cohort, program.name if program else None, program.code if program else None, location)


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

    changes = body.model_dump(exclude_unset=True)
    if changes.get("location_id") and await db.get(Location, changes["location_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Location not found")
    if changes.get("warehouse_id") and await db.get(Warehouse, changes["warehouse_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")

    for field, value in changes.items():
        setattr(cohort, field, value)
    await db.commit()
    await db.refresh(cohort)
    program = await db.get(Program, cohort.program_id)
    location = await db.get(Location, cohort.location_id) if cohort.location_id else None
    return await _cohort_out(db, cohort, program.name if program else None, program.code if program else None, location)


@router.delete("/cohorts/{cohort_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cohort(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Only ever deletes a cohort nobody has signed up for.

    registrations.cohort_id cascades, and attendance cascades from there, so
    an unguarded delete would erase real people's sign-up and attendance
    history without warning. Cancelled registrations count too — a cancellation
    is a record of something that happened, not an empty slot. A cohort that
    ran should be set to `cancelled` or `completed`, not deleted.

    Its sessions (and their instructor assignments) do cascade away, which is
    correct: with no registrations there can be no attendance hanging off them.
    """
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    registration_count = await db.scalar(
        select(func.count()).select_from(Registration).where(Registration.cohort_id == cohort_id)
    )
    if registration_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"This cohort has {registration_count} registration(s) and can't be deleted. "
                "Set its status to cancelled instead — that keeps the students' history."
            ),
        )

    await db.delete(cohort)
    await db.commit()


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

async def _session_out(db: AsyncSession, session: Session, cohort: Cohort | None = None) -> SessionOut:
    rows = (await db.execute(
        select(SessionInstructor, User.full_name, DeliveryRole.name)
        .join(User, User.id == SessionInstructor.user_id)
        .join(DeliveryRole, DeliveryRole.id == SessionInstructor.role_id)
        .where(SessionInstructor.session_id == session.id)
    )).all()
    interest_count = (await db.execute(
        select(func.count())
        .select_from(InstructorInterest)
        .where(InstructorInterest.session_id == session.id)
    )).scalar_one()

    out = SessionOut.model_validate(session)
    out.instructors = [
        SessionInstructorOut(user_id=si.user_id, full_name=name, role=role_name)
        for si, name, role_name in rows
    ]
    out.target_user_ids = await staffing_service.call_target_ids(db, session.id)
    out.interested_count = interest_count

    # Session override wins; otherwise inherit the cohort's location.
    effective_id = session.location_id
    if effective_id is None:
        if cohort is None:
            cohort = await db.get(Cohort, session.cohort_id)
        effective_id = cohort.location_id if cohort else None
    if effective_id:
        location = await db.get(Location, effective_id)
        if location:
            out.effective_location_id = location.id
            out.effective_location_name = location.name

    # Same override chain for warehouse — session, then cohort, then
    # auto-resolve from the effective location if it has exactly one.
    if cohort is None:
        cohort = await db.get(Cohort, session.cohort_id)
    explicit_warehouse_id = session.warehouse_id or (cohort.warehouse_id if cohort else None)
    warehouse = await _resolve_effective_warehouse(
        db, warehouse_id=explicit_warehouse_id, location_id=effective_id
    )
    if warehouse is not None:
        out.effective_warehouse_id = warehouse.id
        out.effective_warehouse_name = warehouse.name

    materials, _ = await materials_service.resolve_for_session(db, session)
    out.materials_count = len(materials)
    kits, _ = await resolve_session_kits(db, session)
    out.kits_count = len(kits)

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
    cohort = await db.get(Cohort, cohort_id)
    result = await db.execute(
        select(Session)
        .where(Session.cohort_id == cohort_id)
        .order_by(Session.meeting_date, Session.starts_at)
    )
    return [await _session_out(db, s, cohort) for s in result.scalars().all()]


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
        duration_hours=body.duration_hours,
    )
    db.add(session)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A session already exists at this date and time")
    await db.commit()
    await db.refresh(session)
    return await _session_out(db, session, cohort)


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

    changes = body.model_dump(exclude_unset=True)
    if changes.get("location_id") and await db.get(Location, changes["location_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Location not found")
    if changes.get("warehouse_id") and await db.get(Warehouse, changes["warehouse_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")

    for field, value in changes.items():
        setattr(session, field, value)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A session already exists at this date and time")
    await db.commit()
    await db.refresh(session)
    return await _session_out(db, session)


@router.delete("/cohorts/{cohort_id}/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    cohort_id: uuid.UUID,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Only ever deletes a session nobody was marked present or absent for —
    attendance_records.session_id cascades. Instructor assignments and any
    registration_sessions rows restricting a registration to this session do
    cascade away, which is what you want when removing a date that was
    scheduled by mistake or generated one too many times.
    """
    session = await db.get(Session, session_id)
    if session is None or session.cohort_id != cohort_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    attendance_count = await db.scalar(
        select(func.count()).select_from(AttendanceRecord).where(AttendanceRecord.session_id == session_id)
    )
    if attendance_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"Attendance has been recorded for {attendance_count} student(s) in this session, "
                "so it can't be deleted."
            ),
        )

    await db.delete(session)
    await db.commit()


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
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
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
    # I5-3: omitted role means the most senior one — what `role="lead"` meant
    # before roles were configurable.
    role_id = body.role_id or await lead_role_id(db)
    if role_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="No delivery roles are configured")
    role = await db.get(DeliveryRole, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Delivery role not found")

    is_new_assignment = existing is None
    if existing is not None:
        existing.role_id = role_id
    else:
        db.add(SessionInstructor(id=uuid.uuid4(), session_id=session_id, user_id=body.user_id, role_id=role_id))
    await db.flush()
    # Direct assign bypasses the open-call/interest marketplace entirely (W4).
    # I5-4: "staffed" means every opening filled; with no openings it falls
    # back to "somebody is assigned", exactly as before.
    session.staffing_status = "staffed" if await fully_staffed(db, session_id) else "open_call"

    # Direct assign used to notify nobody — only the marketplace path
    # (staffing.select_instructors) did. Same notify+email pair here so an
    # instructor finds out regardless of which path put them on the session.
    if is_new_assignment:
        cohort = await db.get(Cohort, cohort_id)
        await create_notification(
            db, body.user_id, "You've been assigned to a session",
            body=f"You're assigned ({role.name}) to a session on {session.meeting_date}"
                 + (f" at {cohort.location}." if cohort and cohort.location else "."),
            type="staffing_assigned",
        )
        await safe_enqueue(arq_redis, "send_assignment_email", str(session_id), str(body.user_id))

    await db.commit()
    return SessionInstructorOut(user_id=user.id, full_name=user.full_name, role=role.name)


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


# ── Bulk session actions (2026-08-01) ───────────────────────────────────────
# A cohort with 100 sessions shouldn't mean 100 taps for the common cases:
# the same instructor onto several sessions, or opening several calls at
# once. Both loop the exact same per-session logic used above/in the
# staffing service — partial failure doesn't roll back the rest of the batch,
# it's reported back per session instead.

@router.post("/cohorts/{cohort_id}/sessions/bulk-assign-instructor", response_model=BulkActionResult)
async def bulk_assign_instructor(
    cohort_id: uuid.UUID,
    body: BulkAssignInstructorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    user = await db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    role_id = body.role_id or await lead_role_id(db)
    if role_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="No delivery roles are configured")
    if await db.get(DeliveryRole, role_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Delivery role not found")

    succeeded: list[uuid.UUID] = []
    failed: list[BulkActionError] = []
    for session_id in dict.fromkeys(body.session_ids):  # de-dupe, keep order
        session = await db.get(Session, session_id)
        if session is None or session.cohort_id != cohort_id:
            failed.append(BulkActionError(session_id=session_id, detail="Session not found in this cohort"))
            continue

        existing = await db.scalar(
            select(SessionInstructor).where(
                SessionInstructor.session_id == session_id, SessionInstructor.user_id == body.user_id,
            )
        )
        if existing is not None:
            existing.role_id = role_id
        else:
            db.add(SessionInstructor(id=uuid.uuid4(), session_id=session_id, user_id=body.user_id, role_id=role_id))
        await db.flush()
        session.staffing_status = "staffed" if await fully_staffed(db, session_id) else "open_call"
        succeeded.append(session_id)

    await db.commit()
    return BulkActionResult(succeeded=succeeded, failed=failed)


@router.post("/cohorts/{cohort_id}/sessions/bulk-open-call", response_model=BulkActionResult)
async def bulk_open_call(
    cohort_id: uuid.UUID,
    body: BulkOpenCallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Same targeting/role-scoping a single "Target Instructors…" call takes,
    applied to every listed session — the ask that "Open Call (All
    Instructors)" and the per-session targeted modal don't cover: a chosen
    subset of sessions, optionally restricted to specific instructors."""
    succeeded: list[uuid.UUID] = []
    failed: list[BulkActionError] = []
    for session_id in dict.fromkeys(body.session_ids):
        session = await db.get(Session, session_id)
        if session is None or session.cohort_id != cohort_id:
            failed.append(BulkActionError(session_id=session_id, detail="Session not found in this cohort"))
            continue
        try:
            await staffing_service.open_call(
                db, session_id, body.target_user_ids, body.role_ids, actor_user_id=current_user.id,
            )
            succeeded.append(session_id)
        except HTTPException as e:
            failed.append(BulkActionError(session_id=session_id, detail=str(e.detail)))

    await db.commit()
    return BulkActionResult(succeeded=succeeded, failed=failed)


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
    certified_ids: set[uuid.UUID] = set()
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
            certified_ids.add(cert.registration_id)
            # resolve_url already prefers a fresh signed URL from (bucket, path)
            # and falls back to a stored file_url — guarding on bucket/path here
            # defeated that fallback, hiding the URL on any row that only has
            # file_url. Student completion certs have neither (emailed, never
            # stored), so they correctly stay None while still being reported
            # as issued via certified_ids.
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
            # Attendance is present|absent; this used to also count "late",
            # which disagreed with the certificate rule's present-only count.
            if status_val == "present":
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
                certificate_issued=reg.id in certified_ids,
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


@router.delete("/registrations/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_registration(
    registration_id: uuid.UUID,
    delete_contact: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Erases a sign-up — attendance and any certificate for it go too.

    Cancel (above) is the safe option: it keeps the row and the history, and
    frees the seat either way since cancelled registrations don't count against
    capacity. Delete is the destructive one, for rows that shouldn't exist —
    a wrong cohort, a duplicate, a typo — and it does not hold back once
    attendance has been taken (operator decision, 2026-07-26). Certificates are
    removed explicitly because certificates.registration_id is SET NULL, so
    they'd otherwise survive as orphans pointing at nobody.

    `delete_contact=true` additionally removes the person from Contacts. Two
    things are refused rather than done quietly, because contacts.id cascades
    to nine tables and a contact is shared across every cohort:

      · a contact linked to a staff user account — deleting the person record
        behind a real login is never what's meant here
      · a contact with registrations in other cohorts — those, and their
        attendance and certificates, would vanish with no warning

    In both cases the operator is told what's attached; deleting the other
    registrations first still gets them a clean removal.
    """
    registration = await db.get(Registration, registration_id)
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Registration not found")

    contact_id = registration.contact_id

    if delete_contact:
        linked_users = await db.scalar(
            select(func.count()).select_from(User).where(User.contact_id == contact_id)
        )
        if linked_users:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    "This person has a staff account on the platform, so their contact can't "
                    "be deleted. The registration alone can still be removed."
                ),
            )

        other_registrations = await db.scalar(
            select(func.count()).select_from(Registration).where(
                Registration.contact_id == contact_id, Registration.id != registration_id,
            )
        )
        if other_registrations:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"This person is registered in {other_registrations} other cohort(s). "
                    "Deleting their contact would erase those registrations and their "
                    "attendance too. Remove those registrations first, or delete this one "
                    "without deleting the contact."
                ),
            )

    await db.execute(
        sa_delete(Certificate).where(Certificate.registration_id == registration_id)
    )
    await db.delete(registration)
    await db.flush()

    if delete_contact:
        contact = await db.get(Contact, contact_id)
        if contact is not None:
            await db.delete(contact)

    await db.commit()


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


@router.get("/cohorts/{cohort_id}/certificates/download")
async def download_cohort_certificates(
    cohort_id: uuid.UUID,
    theme: str = Query("dark", pattern="^(dark|light)$"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """One PDF, one page per *registered* student in this cohort — for
    printing at the workshop, not gated on completion/issuance status (every
    registrant gets a page, same as complete_cohort's auto-issue would
    eventually give them, just generated up front here instead). Cancelled
    registrations are excluded, same convention as list_cohorts' counts.
    Generated fresh each time, nothing persisted or emailed — this is a
    print run, not the student_completion issuance flow in delivery.py.
    `theme` picks the background template (operator ask, 2026-08-07)."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    program = await db.get(Program, cohort.program_id)

    rows = (await db.execute(
        select(Contact.full_name)
        .join(Registration, Registration.contact_id == Contact.id)
        .where(Registration.cohort_id == cohort_id, Registration.status != "cancelled")
        .order_by(Contact.full_name)
    )).scalars().all()
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No registered students in this cohort yet")

    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == "student_completion")
    )).scalars().first()
    template_body = template.body_text if template else "For successfully completing<br/>{program_name}<br/>{dates}"
    body_text = template_body \
        .replace("{program_name}", escape(program.name if program else "")) \
        .replace("{dates}", escape(format_cohort_dates(cohort)))

    def _render(name: str, body: str) -> bytes:
        return generate_completion_certificate_pdf(name, body, theme=theme)

    pages = [await asyncio.to_thread(_render, full_name, body_text) for full_name in rows]

    merged = await asyncio.to_thread(merge_certificate_pdfs, pages)
    safe_name = "".join(c for c in cohort.name if c.isalnum() or c in " -_").strip().replace(" ", "_")
    return Response(
        content=merged, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="certificates_{safe_name or cohort_id}.pdf"'},
    )


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


@router.get("/{session_id}/history")
async def session_history(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """3-phase session audit trail: pre-session, during-session, post-session."""
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    instructors_rows = (await db.execute(
        select(SessionInstructor, User, DeliveryRole)
        .join(User, User.id == SessionInstructor.user_id)
        .join(DeliveryRole, DeliveryRole.id == SessionInstructor.role_id)
        .where(SessionInstructor.session_id == session_id)
    )).all()
    instructor_roles = {u.id: (u.full_name, r.name) for _, u, r in instructors_rows}

    movements = (await db.execute(
        select(Movement)
        .where(Movement.session_id == session_id)
        .order_by(Movement.created_at.asc())
    )).scalars().all()

    loc_ids = {m.from_location_id for m in movements if m.from_location_id} | {m.to_location_id for m in movements if m.to_location_id}
    wh_ids = {m.from_warehouse_id for m in movements if m.from_warehouse_id} | {m.to_warehouse_id for m in movements if m.to_warehouse_id}
    usr_ids = {m.from_user_id for m in movements if m.from_user_id} | {m.to_user_id for m in movements if m.to_user_id} | {m.created_by for m in movements if m.created_by}
    item_ids = {m.item_id for m in movements if m.item_id}
    kit_ids = {m.kit_id for m in movements if m.kit_id}

    locations = {l.id: l.name for l in (await db.execute(select(Location).where(Location.id.in_(loc_ids)))).scalars().all()} if loc_ids else {}
    warehouses = {w.id: w.name for w in (await db.execute(select(Warehouse).where(Warehouse.id.in_(wh_ids)))).scalars().all()} if wh_ids else {}
    users = {u.id: u.full_name for u in (await db.execute(select(User).where(User.id.in_(usr_ids)))).scalars().all()} if usr_ids else {}
    items = {i.id: i.name for i in (await db.execute(select(Item).where(Item.id.in_(item_ids)))).scalars().all()} if item_ids else {}
    kits = {k.id: k.label for k in (await db.execute(select(Kit).where(Kit.id.in_(kit_ids)))).scalars().all()} if kit_ids else {}

    pre_movements = []
    post_movements = []
    for m in movements:
        target_uid = m.from_user_id or m.to_user_id or m.created_by
        inst_name, inst_role = instructor_roles.get(
            target_uid, (users.get(target_uid, "Instructor"), "Instructor")
        )
        entry = {
            "id": str(m.id),
            "reason": m.reason,
            "subject": kits.get(m.kit_id) if m.kit_id else (f"{items.get(m.item_id)} (x{m.qty})" if m.item_id else "Equipment"),
            "is_kit": bool(m.kit_id),
            "qty": m.qty,
            "from_warehouse_name": warehouses.get(m.from_warehouse_id),
            "to_warehouse_name": warehouses.get(m.to_warehouse_id),
            "from_location_name": locations.get(m.from_location_id),
            "to_location_name": locations.get(m.to_location_id),
            "actor_name": inst_name,
            "actor_role": inst_role,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "due_back_on": m.due_back_on.isoformat() if m.due_back_on else None,
            "note": m.note,
        }
        if m.reason == "issue":
            pre_movements.append(entry)
        elif m.reason in ("return", "adjust", "writeoff"):
            post_movements.append(entry)

    kit_checks = (await db.execute(
        select(KitCheck).where(KitCheck.session_id == session_id).order_by(KitCheck.created_at.asc())
    )).scalars().all()

    check_user_ids = {kc.checked_by for kc in kit_checks if kc.checked_by}
    check_users = {u.id: u.full_name for u in (await db.execute(select(User).where(User.id.in_(check_user_ids)))).scalars().all()} if check_user_ids else {}

    pre_checks = []
    post_checks = []
    for kc in kit_checks:
        c_name, c_role = instructor_roles.get(kc.checked_by, (check_users.get(kc.checked_by, "Instructor"), "Instructor"))
        kit_label = kits.get(kc.kit_id, "Kit")
        check_data = {
            "id": str(kc.id),
            "kit_id": str(kc.kit_id),
            "kit_label": kit_label,
            "phase": kc.phase,
            "skipped": kc.skipped,
            "actor_name": c_name,
            "actor_role": c_role,
            "counts": kc.counts,
            "missing": kc.missing,
            "note": kc.note,
            "created_at": kc.created_at.isoformat() if kc.created_at else None,
        }
        if kc.phase == "pre":
            pre_checks.append(check_data)
        else:
            post_checks.append(check_data)

    att_records = (await db.execute(
        select(AttendanceRecord, Registration, Contact)
        .join(Registration, Registration.id == AttendanceRecord.registration_id)
        .join(Contact, Contact.id == Registration.contact_id)
        .where(AttendanceRecord.session_id == session_id)
    )).all()

    att_summary = {"present": 0, "absent": 0, "late": 0, "excused": 0, "total": len(att_records), "records": []}
    for ar, reg, contact in att_records:
        status_val = ar.att_status
        if status_val in att_summary:
            att_summary[status_val] += 1
        att_summary["records"].append({
            "registration_id": str(reg.id),
            "student_name": contact.full_name,
            "status": status_val,
            "marked_at": ar.recorded_at.isoformat() if ar.recorded_at else None,
        })

    reports = (await db.execute(
        select(SessionReport).where(SessionReport.session_id == session_id).order_by(SessionReport.created_at.desc())
    )).scalars().all()
    report_user_ids = {r.uploaded_by for r in reports if r.uploaded_by}
    report_users = {u.id: u.full_name for u in (await db.execute(select(User).where(User.id.in_(report_user_ids)))).scalars().all()} if report_user_ids else {}

    reports_data = []
    for r in reports:
        u_name, u_role = instructor_roles.get(r.uploaded_by, (report_users.get(r.uploaded_by, "Instructor"), "Instructor"))
        url = await storage.resolve_url("reports", r.file_ref)
        reports_data.append({
            "id": str(r.id),
            "file_url": url,
            "notes": r.notes,
            "actor_name": u_name,
            "actor_role": u_role,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    addons = await openings_svc.addons_for_session(db, session_id)

    return {
        "session_id": str(session_id),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        "notes": session.notes,
        "pre_session": {
            "movements": pre_movements,
            "kit_checks": pre_checks,
        },
        "during_session": {
            "attendance": att_summary,
        },
        "post_session": {
            "movements": post_movements,
            "kit_checks": post_checks,
            "reports": reports_data,
            "addons": addons,
        },
    }
