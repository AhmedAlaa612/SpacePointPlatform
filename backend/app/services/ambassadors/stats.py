"""Ambassador stats service — shared by dashboard, admin, leaderboard, and public certificate.

All aggregations are single-pass GROUP BY queries so query count stays flat
regardless of how many ambassadors/teachers exist.

NOTE: The legacy `instructors` table is deprecated. Instructors are now users
with 'instructor' in their `roles` array and `invited_by_id` pointing to the
ambassador who referred them.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import func, and_, cast, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.dialects.postgresql import ARRAY

from app.models.user import User
from app.models.ambassadors.lead import Lead
from app.models.ambassadors.task import AmbassadorTask
from app.models.ambassadors.teacher_session import TeacherSession
from app.models.ambassadors.points_transaction import PointsTransaction


async def ambassador_overview(db: AsyncSession, amb_id) -> dict:
    # Teachers by status (1 query) — role = 'teacher' in roles array
    teacher_rows = (await db.execute(
        select(User.status, func.count())
        .where(and_(
            User.invited_by_id == amb_id,
            User.roles.any("teacher"),
        ))
        .group_by(User.status)
    )).all()
    teachers_by_status = {s: int(c) for s, c in teacher_rows}

    # Instructors by status (1 query) — role = 'instructor' in roles array
    inst_rows = (await db.execute(
        select(User.status, func.count())
        .where(and_(
            User.invited_by_id == amb_id,
            User.roles.any("instructor"),
        ))
        .group_by(User.status)
    )).all()
    inst_by_status = {s: int(c) for s, c in inst_rows}

    # Leads by status (1 query)
    lead_rows = (await db.execute(
        select(Lead.status, func.count())
        .where(Lead.ambassador_id == amb_id)
        .group_by(Lead.status)
    )).all()
    leads_by_status = {s: int(c) for s, c in lead_rows}

    # Ambassador tasks by status (1 query)
    task_rows = (await db.execute(
        select(AmbassadorTask.status, func.count())
        .where(AmbassadorTask.assigned_to == amb_id)
        .group_by(AmbassadorTask.status)
    )).all()
    tasks_by_status = {s: int(c) for s, c in task_rows}

    # Sessions by status with attendance (1 query)
    session_rows = (await db.execute(
        select(TeacherSession.status, func.count(), func.coalesce(func.sum(TeacherSession.attended_students), 0))
        .select_from(TeacherSession)
        .join(User, TeacherSession.teacher_id == User.id)
        .where(User.invited_by_id == amb_id)
        .group_by(TeacherSession.status)
    )).all()
    sessions_by_status = {s: (int(c), int(students)) for s, c, students in session_rows}

    return {
        "active_teachers": teachers_by_status.get("active", 0),
        "pending_teachers": teachers_by_status.get("pending", 0),
        "active_instructors": inst_by_status.get("active", 0),
        "pending_instructors": inst_by_status.get("pending", 0),
        "total_leads": sum(leads_by_status.values()),
        "pending_leads": leads_by_status.get("submitted", 0),
        "converted_leads": leads_by_status.get("converted", 0),
        "pending_tasks": tasks_by_status.get("pending", 0) + tasks_by_status.get("accepted", 0),
        "completed_tasks": tasks_by_status.get("approved", 0),
        "sessions_done": sessions_by_status.get("done", (0, 0))[0],
        "sessions_pending": sessions_by_status.get("pending", (0, 0))[0] + sessions_by_status.get("approved", (0, 0))[0],
        "students_reached": sessions_by_status.get("done", (0, 0))[1],
    }


async def leaderboard(db: AsyncSession, since: Optional[datetime] = None, limit: Optional[int] = None) -> list[dict]:
    """Ambassadors ranked by points. `since` scopes points to a season.
    Six fixed queries regardless of ambassador count."""
    ambassadors = (await db.execute(
        select(User).where(User.roles.any("ambassador"), User.status == "active")
    )).scalars().all()

    pts_q = select(PointsTransaction.ambassador_id, func.sum(PointsTransaction.amount))
    if since is not None:
        pts_q = pts_q.where(PointsTransaction.created_at >= since)
    pts_map = {
        amb_id: int(total or 0)
        for amb_id, total in (await db.execute(pts_q.group_by(PointsTransaction.ambassador_id))).all()
    }

    teachers_map = {
        amb_id: int(c)
        for amb_id, c in (await db.execute(
            select(User.invited_by_id, func.count())
            .where(User.roles.any("teacher"), User.status == "active", User.invited_by_id.isnot(None))
            .group_by(User.invited_by_id)
        )).all()
    }

    instructors_map = {
        amb_id: int(c)
        for amb_id, c in (await db.execute(
            select(User.invited_by_id, func.count())
            .where(User.roles.any("instructor"), User.status == "active", User.invited_by_id.isnot(None))
            .group_by(User.invited_by_id)
        )).all()
    }

    sessions_map = {
        amb_id: (int(c), int(students))
        for amb_id, c, students in (await db.execute(
            select(User.invited_by_id, func.count(), func.coalesce(func.sum(TeacherSession.attended_students), 0))
            .select_from(TeacherSession)
            .join(User, TeacherSession.teacher_id == User.id)
            .where(TeacherSession.status == "done", User.invited_by_id.isnot(None))
            .group_by(User.invited_by_id)
        )).all()
    }

    converted_map = {
        amb_id: int(c)
        for amb_id, c in (await db.execute(
            select(Lead.ambassador_id, func.count())
            .where(Lead.status == "converted")
            .group_by(Lead.ambassador_id)
        )).all()
    }

    out = []
    for amb in ambassadors:
        sessions_done, students = sessions_map.get(amb.id, (0, 0))
        out.append({
            "id": str(amb.id),
            "name": amb.full_name,
            "country": amb.country or "N/A",
            "points": pts_map.get(amb.id, 0),
            "teachers": teachers_map.get(amb.id, 0),
            "instructors": instructors_map.get(amb.id, 0),
            "sessions_done": sessions_done,
            "converted_leads": converted_map.get(amb.id, 0),
            "students_reached": students,
        })

    out.sort(key=lambda r: r["points"], reverse=True)
    if limit:
        out = out[:limit]
    return out


def season_start() -> datetime:
    """Start of the current calendar month (UTC)."""
    from datetime import timezone
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
