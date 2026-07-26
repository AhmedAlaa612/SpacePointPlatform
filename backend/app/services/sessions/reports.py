"""Session reports (V2 W5 S5-2) — a file + notes an instructor or ops
uploads after delivering a session. Reuses the shared storage facade
(services/storage.py), never the local/supabase backends directly.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.cohort import Cohort
from app.models.sessions.session import Session, SessionInstructor
from app.models.sessions.session_report import SessionReport
from app.models.user import User
from app.services import storage

REPORTS_BUCKET = "session-reports"


def display_filename(stored_path: str) -> str:
    """stored_path is "{uuid4().hex}_{original filename}" — uuid4().hex is
    exactly 32 hex chars with no underscore, so split(_, 1) reliably
    recovers the original name even if it contains underscores itself."""
    return stored_path.split("_", 1)[1] if "_" in stored_path else stored_path


async def upload_report(
    db: AsyncSession, cohort_id: uuid.UUID, session_id: uuid.UUID | None,
    file_bytes: bytes, filename: str, content_type: str, notes: str | None, user: User,
) -> SessionReport:
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    is_ops = "operations" in user.role_values or "admin" in user.role_values
    if session_id is not None:
        session = await db.get(Session, session_id)
        if session is None or session.cohort_id != cohort_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found for this cohort")
        if not is_ops:
            assigned = await db.scalar(
                select(SessionInstructor).where(
                    SessionInstructor.session_id == session_id, SessionInstructor.user_id == user.id,
                )
            )
            if assigned is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found for this cohort")
    elif not is_ops:
        # No session_id means a cohort-level report — there's no per-user
        # assignment concept at that level, so only ops/admin may do this
        # (matches complete_cohort's own ops-only, cohort-wide scope).
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Operation not permitted")

    stored_path = f"{uuid.uuid4().hex}_{filename}"
    await storage.upload_to_path(REPORTS_BUCKET, stored_path, file_bytes, content_type)

    report = SessionReport(
        id=uuid.uuid4(), cohort_id=cohort_id, session_id=session_id,
        uploaded_by=user.id, file_ref=stored_path, notes=notes,
    )
    db.add(report)
    await db.flush()
    return report


async def list_reports(db: AsyncSession, cohort_id: uuid.UUID) -> list[tuple[SessionReport, str | None]]:
    """Ops/admin cohort-wide list — role gate is the router's job (this
    mirrors get_cohort/list_registrations, which are also unguarded here)."""
    rows = (await db.execute(
        select(SessionReport, User.full_name)
        .outerjoin(User, User.id == SessionReport.uploaded_by)
        .where(SessionReport.cohort_id == cohort_id)
        .order_by(SessionReport.created_at.desc())
    )).all()
    return [(report, name) for report, name in rows]


async def list_session_reports(db: AsyncSession, session_id: uuid.UUID) -> list[tuple[SessionReport, str | None]]:
    """Session-scoped subset — backs the instructor delivery page. Caller
    (routers/sessions/delivery.py) has already enforced assignment."""
    rows = (await db.execute(
        select(SessionReport, User.full_name)
        .outerjoin(User, User.id == SessionReport.uploaded_by)
        .where(SessionReport.session_id == session_id)
        .order_by(SessionReport.created_at.desc())
    )).all()
    return [(report, name) for report, name in rows]


async def report_count_for_cohort(db: AsyncSession, cohort_id: uuid.UUID) -> int:
    return await db.scalar(
        select(func.count()).select_from(SessionReport).where(SessionReport.cohort_id == cohort_id)
    )


async def resolve_report_url(report: SessionReport) -> str:
    return await storage.get_signed_url(REPORTS_BUCKET, report.file_ref, expires_in=86400)
