"""Check-in scanner endpoints (V2 R2-5) — an operations staff member at the
door scans a ticket's QR (or types the token manually) against a chosen
session. Reuses check_in() from services/sessions/registration.py rather
than reimplementing its 404 (unknown token) / 409 (wrong cohort) / 409 (not
registered for this session) / 409 (already recorded) rules — this router is
a thin wrapper that also resolves the student's name (and program/cohort) for
the result card, since check_in() itself only returns the AttendanceRecord.

Every route is gated by require_operations (admin passes automatically — see
core/dependencies.py's RequireRole), matching this domain's other
operations-only routers (programs.py, cohorts.py). Instructor access to
their own assigned sessions is a later feature, not this one (per this
week's plan).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session
from app.models.spine.contact import Contact
from app.models.user import User
from app.schemas.sessions.checkin import CheckInRequest, CheckInResponse, TodaySessionOut
from app.services.sessions.registration import check_in

router = APIRouter(prefix="/sessions", tags=["sessions-checkin"])


@router.post("/checkin", response_model=CheckInResponse)
async def checkin(
    body: CheckInRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    record = await check_in(db, token=body.token, session_id=body.session_id, actor_user_id=current_user.id)

    # check_in() only returns the AttendanceRecord — walk registration ->
    # contact/cohort/program so the result card can show a name, not just an id.
    registration = await db.get(Registration, record.registration_id)
    contact = await db.get(Contact, registration.contact_id) if registration else None
    cohort = await db.get(Cohort, registration.cohort_id) if registration else None
    program = await db.get(Program, cohort.program_id) if cohort else None

    await db.commit()

    return CheckInResponse(
        attendance_id=record.id,
        att_status=record.att_status,
        method=record.method,
        recorded_at=record.recorded_at,
        student_name=contact.full_name if contact else "Unknown",
        program_name=program.name if program else None,
        cohort_name=cohort.name if cohort else None,
    )


@router.get("/today", response_model=list[TodaySessionOut])
async def list_todays_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Sessions dated today, across every cohort — backs the scanner's "pick
    today's session" step. Uses the server's local date, the same convention
    already used elsewhere in this domain."""
    today = date.today()
    rows = (await db.execute(
        select(Session, Cohort.name, Program.name)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .where(Session.meeting_date == today)
        .order_by(Session.starts_at)
    )).all()
    return [
        TodaySessionOut(
            id=session.id,
            cohort_id=session.cohort_id,
            cohort_name=cohort_name,
            program_name=program_name,
            meeting_date=session.meeting_date,
            starts_at=session.starts_at,
            title=session.title,
        )
        for session, cohort_name, program_name in rows
    ]
