"""Unified, read-only sessions calendar (V2 S6-1).

The ambassadors teacher-session rows are deliberately queried directly and
never written here: their domain remains the source of truth.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.ambassadors.teacher_session import TeacherSession
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.schemas.sessions.calendar import CalendarEventOut, CalendarInstructorOut, CalendarOut
from app.services.sessions.staffing import resolve_session_location_display

router = APIRouter(prefix="/sessions", tags=["sessions-calendar"])


def _delivery_status(session: Session) -> str:
    if session.completed_at:
        return "completed"
    if session.started_at:
        return "in_progress"
    return "scheduled"


@router.get("/calendar", response_model=CalendarOut)
async def get_calendar(
    from_date: date = Query(alias="from"),
    to_date: date = Query(alias="to"),
    scope: Literal["ops", "instructor"] = Query("ops"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if to_date < from_date:
        raise HTTPException(422, detail="to must be on or after from")

    roles = current_user.role_values
    is_ops = "admin" in roles or "operations" in roles
    if scope == "ops" and not is_ops:
        raise HTTPException(403, detail="Operations calendar requires admin or operations role")
    if scope == "instructor" and not is_ops and not ({"instructor", "facilitator"} & set(roles)):
        raise HTTPException(403, detail="Instructor calendar requires instructor or facilitator role")

    stmt = (
        select(Session, Cohort, Program)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .where(Session.meeting_date.between(from_date, to_date))
        .order_by(Session.meeting_date, Session.starts_at)
    )
    if scope == "instructor" and not is_ops:
        stmt = stmt.join(SessionInstructor, SessionInstructor.session_id == Session.id).where(
            SessionInstructor.user_id == current_user.id
        )

    events: list[CalendarEventOut] = []
    for session, cohort, program in (await db.execute(stmt)).all():
        instructor_rows = (await db.execute(
            select(SessionInstructor, User.full_name, DeliveryRole.name)
            .join(User, User.id == SessionInstructor.user_id)
            .join(DeliveryRole, DeliveryRole.id == SessionInstructor.role_id)
            .where(SessionInstructor.session_id == session.id)
            .order_by(DeliveryRole.sort_order, User.full_name)
        )).all()
        starts_at = datetime.combine(session.meeting_date, session.starts_at or time.min, tzinfo=timezone.utc)
        location = await resolve_session_location_display(db, session, cohort)
        events.append(CalendarEventOut(
            id=f"session:{session.id}", source="session", session_id=session.id,
            cohort_id=cohort.id, cohort_name=cohort.name, program_id=program.id,
            program_name=program.name, program_type=program.program_type,
            title=session.title or program.name, starts_at=starts_at, location=location["name"],
            location_address=location["address"],
            location_maps_url=location["maps_url"],
            staffing_status=session.staffing_status, delivery_status=_delivery_status(session),
            instructors=[CalendarInstructorOut(user_id=row.user_id, full_name=name, role=role_name) for row, name, role_name in instructor_rows],
        ))

    # The teacher-session overlay belongs only on the operations view. An
    # instructor's personal view intentionally remains limited to assignments.
    if scope == "ops":
        teachers = (await db.execute(
            select(TeacherSession, User.full_name)
            .join(User, User.id == TeacherSession.teacher_id)
            .where(TeacherSession.date >= datetime.combine(from_date, time.min, tzinfo=timezone.utc))
            .where(TeacherSession.date < datetime.combine(to_date, time.max, tzinfo=timezone.utc))
            .order_by(TeacherSession.date)
        )).all()
        for teacher_session, teacher_name in teachers:
            events.append(CalendarEventOut(
                id=f"teacher_session:{teacher_session.id}", source="teacher_session",
                title=teacher_session.title, starts_at=teacher_session.date,
                teacher_session_status=teacher_session.status, teacher_name=teacher_name,
            ))

    events.sort(key=lambda event: event.starts_at)
    return CalendarOut(from_date=from_date, to_date=to_date, scope=scope, events=events)
