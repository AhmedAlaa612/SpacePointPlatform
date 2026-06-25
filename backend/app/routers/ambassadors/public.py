"""Unauthenticated, shareable ambassador profile / certificate.
Surfaces only non-sensitive impact stats and the earned title."""

import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.models.user import User
from app.models.ambassadors.application_question import ApplicationQuestion
from app.services.ambassadors import stats as stats_service
from app.services.points import lifetime_points
from app.services.ambassadors.titles import resolve_title_progress
from app.services.ambassadors import achievements
from app.schemas.ambassadors.application import ApplicationQuestionOut

router = APIRouter(prefix="/public", tags=["ambassador-public"])


@router.get("/teacher/{teacher_id}")
async def public_teacher_profile(teacher_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Shareable teacher impact certificate (sessions + students, teacher title/badges)."""
    from sqlalchemy import func, and_
    from app.models.ambassadors.teacher_session import TeacherSession

    teacher = (await db.execute(
        select(User).where(
            User.id == teacher_id, User.roles.any("teacher"), User.status == "active"
        )
    )).scalars().first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found")

    sessions_done = await db.scalar(
        select(func.count()).select_from(TeacherSession).where(
            and_(TeacherSession.teacher_id == teacher_id, TeacherSession.status == "done")))
    students_reached = await db.scalar(
        select(func.coalesce(func.sum(TeacherSession.attended_students), 0)).where(
            and_(TeacherSession.teacher_id == teacher_id, TeacherSession.status == "done")))

    points = await lifetime_points(db, teacher.id)
    title_info = await resolve_title_progress(db, points, audience="teacher")
    badges = [b for b in await achievements.list_for(db, teacher.id, audience="teacher") if b["earned"]]

    return {
        "name": teacher.full_name,
        "country": teacher.country,
        "member_since": teacher.created_at.isoformat() if teacher.created_at else None,
        "points": points,
        "title": title_info["current_title"],
        "impact": {
            "sessions_done": int(sessions_done or 0),
            "students_reached": int(students_reached or 0),
        },
        "badges": badges,
    }


@router.get("/ambassador/{ambassador_id}")
async def public_profile(ambassador_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    amb = (await db.execute(
        select(User).where(
            User.id == ambassador_id, User.roles.any("ambassador"), User.status == "active"
        )
    )).scalars().first()
    if not amb:
        raise HTTPException(status_code=404, detail="Ambassador not found")

    points = await lifetime_points(db, amb.id)
    title_info = await resolve_title_progress(db, points)
    overview = await stats_service.ambassador_overview(db, amb.id)
    badges = [b for b in await achievements.list_for(db, amb.id) if b["earned"]]

    return {
        "name": amb.full_name,
        "country": amb.country,
        "member_since": amb.created_at.isoformat() if amb.created_at else None,
        "points": points,
        "title": title_info["current_title"],
        "impact": {
            "active_teachers": overview["active_teachers"],
            "active_instructors": overview["active_instructors"],
            "sessions_done": overview["sessions_done"],
            "students_reached": overview["students_reached"],
            "converted_leads": overview["converted_leads"],
        },
        "badges": badges,
    }


@router.get("/teacher-application-questions", response_model=list[ApplicationQuestionOut])
async def get_teacher_application_questions(db: AsyncSession = Depends(get_db)):
    """Get active teacher application questions."""
    rows = (await db.execute(
        select(ApplicationQuestion)
        .where(ApplicationQuestion.deleted_at == None)  # noqa: E711
        .order_by(ApplicationQuestion.order, ApplicationQuestion.created_at)
    )).scalars().all()
    return rows
