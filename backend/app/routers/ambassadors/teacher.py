from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import func, and_, case, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.models.ambassadors.teacher_session import TeacherSession
from app.models.ambassadors.points_transaction import PointsTransaction
from app.services.points import lifetime_points
from app.services.ambassadors.titles import resolve_title_progress
from app.services.ambassadors import achievements

router = APIRouter(prefix="/teacher", tags=["ambassador-teacher"])


@router.get("/summary")
async def teacher_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Impact stats + supporting ambassador for the logged-in teacher."""
    tid = current_user.id
    now = datetime.now(timezone.utc)

    sessions_done = await db.scalar(
        select(func.count()).select_from(TeacherSession)
        .where(and_(TeacherSession.teacher_id == tid, TeacherSession.status == "done")))
    students_reached = await db.scalar(
        select(func.coalesce(func.sum(TeacherSession.attended_students), 0))
        .where(and_(TeacherSession.teacher_id == tid, TeacherSession.status == "done")))
    pending = await db.scalar(
        select(func.count()).select_from(TeacherSession)
        .where(and_(TeacherSession.teacher_id == tid, TeacherSession.status == "pending")))
    upcoming = await db.scalar(
        select(func.count()).select_from(TeacherSession)
        .where(and_(
            TeacherSession.teacher_id == tid,
            TeacherSession.status == "approved",
            TeacherSession.date >= now,
        )))

    ambassador = None
    if current_user.invited_by_id:
        amb = (await db.execute(select(User).where(User.id == current_user.invited_by_id))).scalars().first()
        if amb:
            ambassador = {"id": str(amb.id), "full_name": amb.full_name, "email": amb.email, "country": amb.country}

    points = await lifetime_points(db, tid)
    title_info = await resolve_title_progress(db, points, audience="teacher")
    badges = await achievements.list_for(db, tid, audience="teacher")

    return {
        "ambassador": ambassador,
        "stats": {
            "sessions_done": int(sessions_done or 0),
            "students_reached": int(students_reached or 0),
            "pending": int(pending or 0),
            "upcoming": int(upcoming or 0),
        },
        "points_balance": points,
        "achievements": badges,
        **title_info,
    }


@router.get("/leaderboard")
async def teacher_leaderboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """All active teachers ranked by students reached, then sessions delivered."""
    done = case((TeacherSession.status == "done", 1), else_=0)
    attended = case((TeacherSession.status == "done", TeacherSession.attended_students), else_=0)

    rows = (await db.execute(
        select(
            User.id, User.full_name, User.country,
            func.coalesce(func.sum(attended), 0).label("students_reached"),
            func.coalesce(func.sum(done), 0).label("sessions_done"),
        )
        .select_from(User)
        .outerjoin(TeacherSession, TeacherSession.teacher_id == User.id)
        .where(User.roles.any("teacher"), User.status == "active")
        .group_by(User.id, User.full_name, User.country)
        .order_by(desc("students_reached"), desc("sessions_done"))
        .limit(100)
    )).all()

    pts_rows = (await db.execute(
        select(PointsTransaction.ambassador_id, func.coalesce(func.sum(PointsTransaction.amount), 0))
        .group_by(PointsTransaction.ambassador_id)
    )).all()
    points_by_user = {uid: int(total) for uid, total in pts_rows}

    result = [
        {
            "id": str(r.id),
            "name": r.full_name,
            "country": r.country or "—",
            "points": points_by_user.get(r.id, 0),
            "students_reached": int(r.students_reached),
            "sessions_done": int(r.sessions_done),
        }
        for r in rows
    ]
    result.sort(key=lambda t: (t["students_reached"], t["points"]), reverse=True)
    return result
