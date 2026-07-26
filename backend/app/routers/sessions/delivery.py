"""Instructor session delivery routers (V2 W5 S5-1) — roster, manual + QR
attendance, start/mark-done. Every route allows the assigned instructor/
facilitator OR ops/admin (require_session_delivery); the actual per-session
assignment check is enforced in services/sessions/delivery.py, not here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_session_delivery
from app.db.session import get_db
from app.models.sessions.program import Program
from app.models.spine.organization import Organization
from app.models.user import User
from app.schemas.sessions.delivery import (
    AttendanceOut,
    MarkAttendanceRequest,
    RosterEntryOut,
    ScanAttendanceRequest,
    SessionDeliveryOut,
)
from app.schemas.sessions.reports import SessionReportOut
from app.services.sessions import delivery
from app.services.sessions import reports as reports_service

router = APIRouter(prefix="/sessions", tags=["sessions-delivery"])


async def _session_delivery_out(db: AsyncSession, session_id: uuid.UUID, user: User) -> SessionDeliveryOut:
    session, cohort, roster = await delivery.get_roster(db, session_id, user)
    program = await db.get(Program, cohort.program_id)

    # Contacts carry organization_id, not a name — resolve the whole roster's
    # organizations in one query rather than per row. (The registrations list
    # in cohorts.py does the equivalent with an aliased join.)
    org_ids = {c.organization_id for _, c, _ in roster if c.organization_id is not None}
    org_names: dict[uuid.UUID, str] = {}
    if org_ids:
        org_names = {
            org.id: org.name_latin
            for org in (await db.execute(
                select(Organization).where(Organization.id.in_(org_ids))
            )).scalars().all()
        }
    report_rows = await reports_service.list_session_reports(db, session_id)
    return SessionDeliveryOut(
        id=session.id, cohort_id=cohort.id, cohort_name=cohort.name, program_name=program.name,
        location=cohort.location, meeting_date=session.meeting_date, starts_at=session.starts_at,
        title=session.title, material_url=session.material_url, started_at=session.started_at, completed_at=session.completed_at,
        roster=[
            RosterEntryOut(
                registration_id=reg.id, contact_id=contact.id, student_name=contact.full_name,
                student_phone=contact.primary_phone_e164,
                student_email=contact.email,
                student_date_of_birth=contact.date_of_birth.isoformat() if contact.date_of_birth else None,
                student_grade=contact.grade,
                student_organization_name=org_names.get(contact.organization_id),
                att_status=att.att_status if att else None,
                att_method=att.method if att else None,
                recorded_at=att.recorded_at if att else None,
            )
            for reg, contact, att in roster
        ],
        reports=[
            SessionReportOut(
                id=report.id, cohort_id=report.cohort_id, session_id=report.session_id,
                uploaded_by=report.uploaded_by, uploaded_by_name=uploader_name,
                file_url=await reports_service.resolve_report_url(report),
                filename=reports_service.display_filename(report.file_ref),
                notes=report.notes, created_at=report.created_at,
            )
            for report, uploader_name in report_rows
        ],
    )


@router.get("/{session_id}/delivery", response_model=SessionDeliveryOut)
async def get_session_delivery(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    return await _session_delivery_out(db, session_id, current_user)


@router.post("/{session_id}/delivery/start", response_model=SessionDeliveryOut)
async def start_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await delivery.start_session(db, session_id, current_user)
    await db.commit()
    return await _session_delivery_out(db, session_id, current_user)


@router.post("/{session_id}/delivery/done", response_model=SessionDeliveryOut)
async def mark_session_done(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await delivery.mark_done(db, session_id, current_user)
    await db.commit()
    return await _session_delivery_out(db, session_id, current_user)


@router.put("/{session_id}/delivery/attendance/{registration_id}", response_model=AttendanceOut)
async def mark_attendance(
    session_id: uuid.UUID,
    registration_id: uuid.UUID,
    body: MarkAttendanceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    record, contact = await delivery.mark_attendance(db, session_id, registration_id, body.att_status, current_user)
    await db.commit()
    return AttendanceOut(
        registration_id=record.registration_id, student_name=contact.full_name,
        att_status=record.att_status, method=record.method, recorded_at=record.recorded_at,
    )


@router.post("/{session_id}/delivery/scan", response_model=AttendanceOut)
async def scan_attendance(
    session_id: uuid.UUID,
    body: ScanAttendanceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    record, contact = await delivery.scan_attendance(db, session_id, body.token, current_user)
    await db.commit()
    return AttendanceOut(
        registration_id=record.registration_id, student_name=contact.full_name,
        att_status=record.att_status, method=record.method, recorded_at=record.recorded_at,
    )
