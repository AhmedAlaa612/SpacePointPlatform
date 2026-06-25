"""Milestone badges. Definitions live in the DB (`badge_definitions`) and are
admin-configurable. A badge unlocks when an ambassador's `criteria_type` metric
reaches its `threshold`. Distinct from Titles, which track cumulative points.

`check_and_grant` is cheap and idempotent — call it after any event that could
unlock a badge."""

import logging
from sqlalchemy import func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.ambassadors.achievement import Achievement
from app.models.ambassadors.badge_definition import BadgeDefinition
from app.models.ambassadors.lead import Lead
from app.models.ambassadors.teacher_session import TeacherSession
from app.models.ambassadors.points_transaction import PointsTransaction
from app.models.user import User
from app.services.notification import create_notification as notify

logger = logging.getLogger("achievements")

CRITERIA_TYPES = [
    "converted_leads",
    "active_teachers",
    "sessions_done",
    "students_reached",
    "lifetime_points",
]

# Teacher badges use teacher-scoped metrics (their own sessions, not a network's).
TEACHER_CRITERIA_TYPES = [
    "sessions_done",
    "students_reached",
    "lifetime_points",
]

CRITERIA_BY_AUDIENCE = {
    "ambassador": CRITERIA_TYPES,
    "teacher": TEACHER_CRITERIA_TYPES,
}


async def _teacher_metrics(db: AsyncSession, teacher_id) -> dict:
    sessions_done = await db.scalar(
        select(func.count()).select_from(TeacherSession).where(
            and_(TeacherSession.teacher_id == teacher_id, TeacherSession.status == "done")))
    students_reached = await db.scalar(
        select(func.coalesce(func.sum(TeacherSession.attended_students), 0)).where(
            and_(TeacherSession.teacher_id == teacher_id, TeacherSession.status == "done")))
    lifetime_points = await db.scalar(
        select(func.coalesce(func.sum(PointsTransaction.amount), 0))
        .where(PointsTransaction.ambassador_id == teacher_id))
    return {
        "sessions_done": int(sessions_done or 0),
        "students_reached": int(students_reached or 0),
        "lifetime_points": int(lifetime_points or 0),
    }


async def _metrics(db: AsyncSession, ambassador_id) -> dict:
    converted_leads = await db.scalar(
        select(func.count()).select_from(Lead).where(
            and_(Lead.ambassador_id == ambassador_id, Lead.status == "converted")))
    active_teachers = await db.scalar(
        select(func.count()).select_from(User).where(
            and_(User.invited_by_id == ambassador_id, User.roles.any("teacher"), User.status == "active")))
    sessions_done = await db.scalar(
        select(func.count()).select_from(TeacherSession)
        .join(User, TeacherSession.teacher_id == User.id)
        .where(and_(User.invited_by_id == ambassador_id, TeacherSession.status == "done")))
    students_reached = await db.scalar(
        select(func.coalesce(func.sum(TeacherSession.attended_students), 0))
        .select_from(TeacherSession)
        .join(User, TeacherSession.teacher_id == User.id)
        .where(and_(User.invited_by_id == ambassador_id, TeacherSession.status == "done")))
    lifetime_points = await db.scalar(
        select(func.coalesce(func.sum(PointsTransaction.amount), 0))
        .where(PointsTransaction.ambassador_id == ambassador_id))
    return {
        "converted_leads": int(converted_leads or 0),
        "active_teachers": int(active_teachers or 0),
        "sessions_done": int(sessions_done or 0),
        "students_reached": int(students_reached or 0),
        "lifetime_points": int(lifetime_points or 0),
    }


async def _definitions(db: AsyncSession, audience: str = "ambassador") -> list[BadgeDefinition]:
    return list((await db.execute(
        select(BadgeDefinition)
        .where(BadgeDefinition.audience == audience)
        .order_by(BadgeDefinition.sort_order.asc(), BadgeDefinition.threshold.asc())
    )).scalars().all())


async def check_and_grant(db: AsyncSession, ambassador_id, audience: str = "ambassador"):
    """Grant any newly-earned badges. Idempotent. Caller commits."""
    defs = await _definitions(db, audience)
    if not defs:
        return
    if audience == "teacher":
        metrics = await _teacher_metrics(db, ambassador_id)
    else:
        metrics = await _metrics(db, ambassador_id)
    earned = {d.code for d in defs if metrics.get(d.criteria_type, 0) >= d.threshold}
    if not earned:
        return

    existing = set((await db.execute(
        select(Achievement.code).where(Achievement.ambassador_id == ambassador_id)
    )).scalars().all())

    by_code = {d.code: d for d in defs}
    for code in earned - existing:
        db.add(Achievement(ambassador_id=ambassador_id, code=code))
        d = by_code.get(code)
        await notify(db, ambassador_id, "Badge unlocked!", f"You earned the '{d.label if d else code}' badge.")
        logger.info(f"Granted achievement {code} to {ambassador_id}")


async def list_for(db: AsyncSession, ambassador_id, audience: str = "ambassador") -> list[dict]:
    """Every badge definition + whether this user has earned it."""
    defs = await _definitions(db, audience)
    rows = (await db.execute(
        select(Achievement).where(Achievement.ambassador_id == ambassador_id)
    )).scalars().all()
    earned_at = {r.code: r.created_at for r in rows}
    out = []
    for d in defs:
        out.append({
            "code": d.code,
            "label": d.label,
            "description": d.description or "",
            "icon": d.icon or "Award",
            "earned": d.code in earned_at,
            "earned_at": earned_at[d.code].isoformat() if d.code in earned_at else None,
        })
    return out
