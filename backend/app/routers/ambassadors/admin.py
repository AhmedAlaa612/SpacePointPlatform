"""Ambassadors admin (Phase 2 gap, built later): network tree, activity feed,
points/leaderboard views, ambassador/teacher deep-dive stats, reward settings,
application-questions CRUD, and a read-only instructors list.

Tasks/Leads/Sessions/Titles/Badges/teacher-applications already have full
admin-aware backends in tasks.py/leads.py/network.py/titles.py/badges.py —
nothing duplicated here. Users CRUD is generic and already lives at
/interns/admin/users (the `users` table is shared, not domain-specific).
Instructor *approval* lives solely in /instructors/admin — this router only
ever reads instructor data for display.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.ambassadors.lead import Lead
from app.models.ambassadors.points_transaction import PointsTransaction
from app.models.ambassadors.system_setting import SystemSetting
from app.models.ambassadors.task import AmbassadorTask
from app.models.ambassadors.teacher_session import TeacherSession
from app.models.user import User
from app.services.ambassadors import stats as stats_service
from app.services.ambassadors import achievements as ach_service
from app.services.ambassadors.titles import resolve_title_progress
from app.services.notification import create_notification as notify
from app.services.points import award_points, get_setting_int, lifetime_points

router = APIRouter(prefix="/admin", tags=["ambassadors-admin"])


# ── Network ────────────────────────────────────────────────────

@router.get("/network")
async def full_network(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    """Whole platform: every active ambassador with their teachers + the
    instructors they referred. Instructors are unified Users with 'instructor'
    in roles[] and invited_by_id pointing at the referring ambassador — there
    is no separate Instructor model (PLAN §9.3)."""
    ambassadors = (await db.execute(
        select(User).where(User.roles.any("ambassador"), User.status == "active").order_by(User.full_name)
    )).scalars().all()
    teachers = (await db.execute(select(User).where(User.roles.any("teacher")))).scalars().all()
    instructors = (await db.execute(select(User).where(User.roles.any("instructor")))).scalars().all()

    done_rows = (await db.execute(
        select(TeacherSession.teacher_id, func.count())
        .where(TeacherSession.status == "done")
        .group_by(TeacherSession.teacher_id)
    )).all()
    done_by_teacher = {tid: cnt for tid, cnt in done_rows}

    by_amb_teachers: dict = {}
    for t in teachers:
        by_amb_teachers.setdefault(t.invited_by_id, []).append(t)
    by_amb_instructors: dict = {}
    for i in instructors:
        by_amb_instructors.setdefault(i.invited_by_id, []).append(i)

    return {
        "ambassadors": [
            {
                "id": str(a.id),
                "full_name": a.full_name,
                "teachers": [
                    {"id": str(t.id), "full_name": t.full_name, "status": t.status,
                     "sessions_done": int(done_by_teacher.get(t.id, 0))}
                    for t in by_amb_teachers.get(a.id, [])
                ],
                "instructors": [
                    {"id": str(i.id), "full_name": i.full_name, "status": i.status}
                    for i in by_amb_instructors.get(a.id, [])
                ],
            }
            for a in ambassadors
        ]
    }


@router.get("/ambassadors/{ambassador_id}/network")
async def ambassador_network(
    ambassador_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    amb = (await db.execute(
        select(User).where(User.id == ambassador_id, User.roles.any("ambassador"))
    )).scalars().first()
    if not amb:
        raise HTTPException(status_code=404, detail="Ambassador not found")

    teachers = (await db.execute(
        select(User).where(User.roles.any("teacher"), User.invited_by_id == ambassador_id)
    )).scalars().all()
    instructors = (await db.execute(
        select(User).where(User.roles.any("instructor"), User.invited_by_id == ambassador_id)
    )).scalars().all()
    sessions_rows = (await db.execute(
        select(TeacherSession, User.full_name)
        .join(User, TeacherSession.teacher_id == User.id)
        .where(User.invited_by_id == ambassador_id)
    )).all()

    return {
        "ambassador": {"id": str(amb.id), "full_name": amb.full_name},
        "teachers": [
            {"id": str(t.id), "full_name": t.full_name, "email": t.email, "status": t.status,
             "created_at": t.created_at.isoformat() if t.created_at else None}
            for t in teachers
        ],
        "instructors": [
            {"id": str(i.id), "full_name": i.full_name, "email": i.email, "status": i.status}
            for i in instructors
        ],
        "sessions": [
            {
                "id": str(s.id), "teacher_id": str(s.teacher_id), "title": s.title, "status": s.status,
                "date": s.date.isoformat() if s.date else None, "attended_students": s.attended_students,
                "teacher_name": tname,
            }
            for s, tname in sessions_rows
        ],
    }


@router.get("/instructors")
async def list_instructors(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    """Read-only — instructor *approval* lives in /instructors/admin."""
    rows = (await db.execute(
        select(User)
        .where(User.roles.any("instructor"))
        .order_by(User.created_at.desc())
    )).scalars().all()
    amb_ids = {u.invited_by_id for u in rows if u.invited_by_id}
    amb_names = {}
    if amb_ids:
        amb_names = dict((await db.execute(
            select(User.id, User.full_name).where(User.id.in_(amb_ids))
        )).all())
    return [
        {
            "id": str(u.id), "full_name": u.full_name, "email": u.email, "status": u.status,
            "invited_by_id": str(u.invited_by_id) if u.invited_by_id else None,
            "ambassador_name": amb_names.get(u.invited_by_id),
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in rows
    ]


# ── Activity feed ──────────────────────────────────────────────

@router.get("/activity")
async def activity_log(limit: int = 60, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    """Platform-wide feed merged from points, leads, tasks, sessions, signups."""
    events: list[dict] = []

    def add(created_at, kind, text, actor=None, amount=None):
        if created_at is None:
            return
        events.append({"created_at": created_at, "kind": kind, "text": text, "actor": actor, "amount": amount})

    for pt, name in (await db.execute(
        select(PointsTransaction, User.full_name)
        .outerjoin(User, PointsTransaction.ambassador_id == User.id)
        .order_by(PointsTransaction.created_at.desc()).limit(limit)
    )).all():
        add(pt.created_at, "points", pt.reason, name, pt.amount)

    for ld, name in (await db.execute(
        select(Lead, User.full_name)
        .outerjoin(User, Lead.ambassador_id == User.id)
        .order_by(Lead.created_at.desc()).limit(limit)
    )).all():
        add(ld.created_at, "lead", f"submitted lead — {ld.company or ld.contact_name} ({ld.status})", name)

    for tk, name in (await db.execute(
        select(AmbassadorTask, User.full_name)
        .outerjoin(User, AmbassadorTask.assigned_to == User.id)
        .order_by(AmbassadorTask.created_at.desc()).limit(limit)
    )).all():
        add(tk.created_at, "task", f"task '{tk.title}' ({tk.status})", name)

    for ss, name in (await db.execute(
        select(TeacherSession, User.full_name)
        .outerjoin(User, TeacherSession.teacher_id == User.id)
        .order_by(TeacherSession.created_at.desc()).limit(limit)
    )).all():
        add(ss.created_at, "session", f"session '{ss.title}' ({ss.status})", name)

    for u in (await db.execute(
        select(User).where(~User.roles.any("admin")).order_by(User.created_at.desc()).limit(limit)
    )).scalars().all():
        add(u.created_at, "signup", f"joined as {'/'.join(u.role_values)} ({u.status})", u.full_name)

    events.sort(key=lambda e: e["created_at"], reverse=True)
    return [
        {"created_at": e["created_at"].isoformat(), "kind": e["kind"], "text": e["text"],
         "actor": e["actor"], "amount": e["amount"]}
        for e in events[:limit]
    ]


# ── User status (approve pending ambassador/teacher signups) ───

class UserStatusUpdate(BaseModel):
    status: str


@router.put("/users/{user_id}/status")
async def update_user_status(
    user_id: uuid.UUID, body: UserStatusUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if (body.status == "active" and "teacher" in user.role_values
            and user.invited_by_id and not user.recruit_points_awarded):
        reward = await get_setting_int(db, "teacher_points_reward", 500)
        await award_points(db, user.invited_by_id, reward, f"Recruited teacher: {user.full_name}")
        user.recruit_points_awarded = True
        await notify(db, user.invited_by_id, "Points Earned!", f"You earned {reward} points for recruiting {user.full_name}.", type="ambassador")

    activated_teacher_of = user.invited_by_id if (
        body.status == "active" and user.status != "active" and "teacher" in user.role_values
    ) else None
    user.status = body.status
    if body.status == "active":
        await notify(db, user.id, "Account Activated", "Your account was activated by an administrator.", type="ambassador")
    if activated_teacher_of:
        await db.flush()
        await ach_service.check_and_grant(db, activated_teacher_of)
    await db.commit()
    await db.refresh(user)
    return {"id": str(user.id), "full_name": user.full_name, "status": user.status}


# ── Leaderboard & points log ──────────────────────────────────

@router.get("/leaderboard")
async def admin_leaderboard(season: bool = False, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    since = stats_service.season_start() if season else None
    return await stats_service.leaderboard(db, since=since)


@router.get("/points-log")
async def points_log(
    limit: int = 200, offset: int = 0, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    rows = (await db.execute(
        select(PointsTransaction, User.full_name, User.email)
        .join(User, PointsTransaction.ambassador_id == User.id)
        .order_by(PointsTransaction.created_at.desc())
        .offset(offset).limit(min(limit, 500))
    )).all()
    return [
        {"id": str(t.id), "amount": t.amount, "type": t.type, "reason": t.reason,
         "created_at": t.created_at.isoformat(), "ambassador_name": name, "ambassador_email": email}
        for t, name, email in rows
    ]


@router.get("/users/{user_id}/points-log")
async def user_points_log(user_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    rows = (await db.execute(
        select(PointsTransaction).where(PointsTransaction.ambassador_id == user_id)
        .order_by(PointsTransaction.created_at.desc())
    )).scalars().all()
    return [
        {"id": str(r.id), "amount": r.amount, "type": r.type, "reason": r.reason,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]


# ── Ambassador / teacher deep stats (AdminAmbassador page) ────

@router.get("/users/{user_id}/ambassador-stats")
async def ambassador_stats(user_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    amb = (await db.execute(select(User).where(User.id == user_id, User.roles.any("ambassador")))).scalars().first()
    if not amb:
        raise HTTPException(status_code=404, detail="Ambassador not found")
    overview = await stats_service.ambassador_overview(db, user_id)
    points = await lifetime_points(db, user_id)
    season_pts = await lifetime_points(db, user_id, since=stats_service.season_start())
    title_info = await resolve_title_progress(db, points)
    badges = await ach_service.list_for(db, user_id)
    teachers = (await db.execute(
        select(User).where(User.roles.any("teacher"), User.invited_by_id == user_id).order_by(User.created_at.desc())
    )).scalars().all()

    full = await stats_service.leaderboard(db)
    rank = next((i + 1 for i, r in enumerate(full) if r["id"] == str(user_id)), None)

    return {
        "ambassador": {
            "id": str(amb.id), "full_name": amb.full_name, "email": amb.email, "country": amb.country,
            "status": amb.status, "invite_code": amb.invite_code,
        },
        "points": {"balance": points, "total_earned": points, "season": season_pts},
        "rank": rank,
        "overview": overview,
        "achievements": badges,
        "teachers": [
            {"id": str(t.id), "full_name": t.full_name, "email": t.email, "status": t.status} for t in teachers
        ],
        **title_info,
    }


@router.get("/users/{user_id}/teacher-stats")
async def teacher_stats(user_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    teacher = (await db.execute(select(User).where(User.id == user_id, User.roles.any("teacher")))).scalars().first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")
    ambassador = None
    if teacher.invited_by_id:
        ambassador = (await db.execute(select(User).where(User.id == teacher.invited_by_id))).scalars().first()
    sessions = (await db.execute(
        select(TeacherSession).where(TeacherSession.teacher_id == user_id).order_by(TeacherSession.date.desc())
    )).scalars().all()
    stats = {
        "total": len(sessions),
        "pending": sum(1 for s in sessions if s.status == "pending"),
        "approved": sum(1 for s in sessions if s.status == "approved"),
        "done": sum(1 for s in sessions if s.status == "done"),
    }
    return {
        "teacher": {"id": str(teacher.id), "full_name": teacher.full_name, "email": teacher.email},
        "ambassador": {"full_name": ambassador.full_name, "email": ambassador.email} if ambassador else None,
        "sessions_stats": stats,
        "sessions": [
            {"id": str(s.id), "title": s.title, "date": s.date.isoformat(), "status": s.status,
             "attended_students": s.attended_students}
            for s in sessions
        ],
    }


# ── Settings ────────────────────────────────────────────────────

class SettingUpdate(BaseModel):
    value: str


@router.get("/settings")
async def get_settings(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    rows = (await db.execute(select(SystemSetting))).scalars().all()
    return {r.key: r.value for r in rows}


@router.put("/settings/{key}")
async def update_setting(
    key: str, body: SettingUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    setting = (await db.execute(select(SystemSetting).where(SystemSetting.key == key))).scalars().first()
    if setting:
        setting.value = body.value
    else:
        db.add(SystemSetting(key=key, value=body.value))
    await db.commit()
    return {"key": key, "value": body.value}

