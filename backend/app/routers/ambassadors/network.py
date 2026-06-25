import uuid
import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import and_

from app.db.session import get_db
from app.core.dependencies import get_current_active_user, require_ambassador, require_teacher
from app.core.security import get_password_hash
from app.models.user import User
from app.models.ambassadors.teacher_session import TeacherSession
from app.models.ambassadors.teacher_application import TeacherApplication
from app.schemas.ambassadors.network import (
    StatusUpdate, SessionCreate, SessionDone, SessionUpdate, MaterialSent,
    SessionCancel, SessionReject, TeacherOut, InstructorOut, SessionOut,
)
from app.schemas.ambassadors.application import TeacherApplicationOut
from app.services.points import award_points, adjust_points, get_setting_int
from app.services.notification import create_notification as notify
from app.services.ambassadors import achievements

logger = logging.getLogger("network")
router = APIRouter(prefix="/network", tags=["ambassador-network"])


# ── Teachers ──────────────────────────────────────────────────

@router.get("/teachers", response_model=list[TeacherOut])
async def my_teachers(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_ambassador)):
    rows = (await db.execute(
        select(User).where(
            User.roles.any("teacher"), User.invited_by_id == current_user.id
        ).order_by(User.created_at.desc())
    )).scalars().all()
    return list(rows)


@router.get("/teachers/{teacher_id}", response_model=TeacherOut)
async def get_teacher(
    teacher_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ambassador),
):
    teacher = (await db.execute(
        select(User).where(
            User.id == teacher_id, User.roles.any("teacher"), User.invited_by_id == current_user.id
        )
    )).scalars().first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found or not in your network")
    return teacher


@router.put("/teachers/{teacher_id}/status", response_model=TeacherOut)
async def update_teacher_status(
    teacher_id: uuid.UUID,
    body: StatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ambassador),
):
    if body.status not in ("active", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be 'active' or 'rejected'")

    teacher = (await db.execute(
        select(User).where(
            User.id == teacher_id, User.roles.any("teacher"), User.invited_by_id == current_user.id
        )
    )).scalars().first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher not found or not in your network")

    if body.status == "active" and not teacher.recruit_points_awarded:
        reward = await get_setting_int(db, "teacher_points_reward", 500)
        await award_points(db, current_user.id, reward, f"Recruited teacher: {teacher.full_name}")
        teacher.recruit_points_awarded = True
        await notify(db, current_user.id, "Points Earned!", f"You earned {reward} points for recruiting {teacher.full_name}.")

    teacher.status = body.status
    if body.status == "active":
        await notify(db, teacher.id, "Application Approved", "Your teacher application was approved — welcome aboard!")
    await db.flush()
    if body.status == "active":
        await achievements.check_and_grant(db, current_user.id)
    await db.commit()
    await db.refresh(teacher)
    return teacher


# ── Instructors (unified users with instructor role) ─────────

@router.get("/instructors", response_model=list[InstructorOut])
async def my_instructors(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_ambassador)):
    rows = (await db.execute(
        select(User).where(
            User.roles.any("instructor"), User.invited_by_id == current_user.id
        ).order_by(User.created_at.desc())
    )).scalars().all()
    return list(rows)


# ── Sessions ──────────────────────────────────────────────────

@router.get("/all-sessions", response_model=list[SessionOut])
async def all_sessions(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_ambassador)):
    rows = (await db.execute(
        select(TeacherSession, User.full_name, User.email)
        .join(User, TeacherSession.teacher_id == User.id)
        .where(User.invited_by_id == current_user.id)
        .order_by(TeacherSession.date.desc())
    )).all()
    out = []
    for s, name, email in rows:
        d = SessionOut.model_validate(s)
        d.teacher_name, d.teacher_email = name, email
        out.append(d)
    return out


@router.get("/teachers/{teacher_id}/sessions", response_model=list[SessionOut])
async def teacher_sessions(
    teacher_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if "admin" in current_user.role_values:
        pass
    elif "ambassador" in current_user.role_values:
        owns = (await db.execute(
            select(User.id).where(
                User.id == teacher_id, User.roles.any("teacher"), User.invited_by_id == current_user.id
            )
        )).first()
        if not owns:
            raise HTTPException(status_code=403, detail="This teacher is not in your network")
    elif "teacher" in current_user.role_values and current_user.id != teacher_id:
        raise HTTPException(status_code=403, detail="You can only view your own sessions")

    rows = (await db.execute(
        select(TeacherSession).where(TeacherSession.teacher_id == teacher_id).order_by(TeacherSession.date.asc())
    )).scalars().all()
    return list(rows)


@router.post("/teachers/{teacher_id}/sessions", response_model=SessionOut, status_code=201)
async def create_session(
    teacher_id: uuid.UUID,
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    if "admin" not in current_user.role_values and current_user.id != teacher_id:
        raise HTTPException(status_code=403, detail="You can only add sessions for yourself")

    session = TeacherSession(
        teacher_id=teacher_id, title=body.title, description=body.description, date=body.date,
        planned_students=body.planned_students, status="pending", material_sent=False,
    )
    db.add(session)
    if current_user.invited_by_id:
        await notify(db, current_user.invited_by_id, "New Session Submitted",
                     f"{current_user.full_name} submitted a session: {body.title}.")
    await db.commit()
    await db.refresh(session)
    return session


async def _session_in_network(db: AsyncSession, session_id, user: User):
    """The session's recruiting ambassador — or any admin — may manage it."""
    row = (await db.execute(
        select(TeacherSession, User.invited_by_id)
        .join(User, TeacherSession.teacher_id == User.id)
        .where(TeacherSession.id == session_id)
    )).first()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    session, invited_by = row
    if "admin" not in user.role_values and invited_by != user.id:
        raise HTTPException(status_code=403, detail="This session is not from your network")
    return session


@router.put("/sessions/{session_id}/approve", response_model=SessionOut)
async def approve_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_ambassador)):
    session = await _session_in_network(db, session_id, current_user)
    if session.status != "pending":
        raise HTTPException(status_code=400, detail="Session is not pending")
    session.status = "approved"
    session.status_note = None
    await notify(db, session.teacher_id, "Session Approved", f"Your session '{session.title}' was approved.")
    await db.commit()
    await db.refresh(session)
    return session


@router.put("/sessions/{session_id}/reject", response_model=SessionOut)
async def reject_session(
    session_id: uuid.UUID,
    body: SessionReject | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ambassador),
):
    session = await _session_in_network(db, session_id, current_user)
    if session.status not in ("pending", "approved"):
        raise HTTPException(status_code=400, detail="Only pending or approved sessions can be rejected")
    session.status = "rejected"
    session.status_note = (body.reason or "").strip() or None if body else None
    await notify(db, session.teacher_id, "Session Rejected", f"Your session '{session.title}' was rejected.")
    await db.commit()
    await db.refresh(session)
    return session


@router.put("/sessions/{session_id}/material-sent", response_model=SessionOut)
async def material_sent(
    session_id: uuid.UUID,
    body: MaterialSent | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ambassador),
):
    session = await _session_in_network(db, session_id, current_user)
    if session.status != "approved":
        raise HTTPException(status_code=400, detail="Session must be approved before sending material")
    session.material_sent = True
    if body and body.material_link is not None:
        session.material_link = body.material_link.strip() or None
    await db.commit()
    await db.refresh(session)
    return session


@router.put("/sessions/{session_id}/done", response_model=SessionOut)
async def mark_done(
    session_id: uuid.UUID,
    body: SessionDone,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_teacher),
):
    session = (await db.execute(
        select(TeacherSession).where(TeacherSession.id == session_id)
    )).scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if "admin" not in current_user.role_values and session.teacher_id != current_user.id:
        raise HTTPException(status_code=403, detail="You can only mark your own sessions as done")
    if session.status != "approved" or not session.material_sent:
        raise HTTPException(status_code=400, detail="Session must be approved and material sent before completion")
    if session.date > datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="A session can't be marked delivered before its scheduled date")

    session.status = "done"
    session.attended_students = body.attended_students
    session.points_awarded = True

    reward = await get_setting_int(db, "session_points_reward", 200)
    await award_points(db, current_user.id, reward, f"Session delivered: {session.title}")

    if current_user.invited_by_id:
        await award_points(db, current_user.invited_by_id, reward, f"Teacher session completed: {session.title}")
        await notify(db, current_user.invited_by_id, "Points Earned!",
                     f"You earned {reward} points — {current_user.full_name} completed a session.")

    await db.flush()
    if current_user.invited_by_id:
        await achievements.check_and_grant(db, current_user.invited_by_id)
    await achievements.check_and_grant(db, current_user.id, audience="teacher")

    await db.commit()
    await db.refresh(session)
    return session


async def _own_editable_session(db: AsyncSession, session_id: uuid.UUID, user: User) -> TeacherSession:
    session = (await db.execute(select(TeacherSession).where(TeacherSession.id == session_id))).scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if "admin" not in user.role_values and session.teacher_id != user.id:
        raise HTTPException(status_code=403, detail="Only the session's teacher or an admin can do this")
    return session


@router.patch("/sessions/{session_id}", response_model=SessionOut)
async def edit_session(
    session_id: uuid.UUID,
    body: SessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    session = await _own_editable_session(db, session_id, current_user)
    if session.status in ("done", "cancelled"):
        raise HTTPException(status_code=400, detail="A completed or cancelled session can't be edited")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(session, k, v)

    if "teacher" in current_user.role_values and session.status in ("approved", "rejected"):
        was = session.status
        session.status = "pending"
        session.status_note = None
        teacher = current_user
        if teacher.invited_by_id:
            verb = "resubmitted" if was == "rejected" else "updated"
            await notify(db, teacher.invited_by_id, "Session Needs Re-approval",
                         f"{teacher.full_name} {verb} the session '{session.title}' — please review it again.")

    await db.commit()
    await db.refresh(session)
    return session


@router.put("/sessions/{session_id}/cancel", response_model=SessionOut)
async def cancel_session(
    session_id: uuid.UUID,
    body: SessionCancel | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    session = await _own_editable_session(db, session_id, current_user)
    if session.status in ("done", "cancelled"):
        raise HTTPException(status_code=400, detail="This session can't be cancelled")
    session.status = "cancelled"
    session.status_note = (body.reason or "").strip() or None if body else None

    teacher = (await db.execute(select(User).where(User.id == session.teacher_id))).scalars().first()
    if teacher and teacher.invited_by_id:
        reason = f" Reason: {session.status_note}" if session.status_note else ""
        await notify(db, teacher.invited_by_id, "Session Cancelled",
                     f"{teacher.full_name} cancelled the session '{session.title}'.{reason}")
    await db.commit()
    await db.refresh(session)
    return session


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    session = await _own_editable_session(db, session_id, current_user)
    if session.status == "done" and "admin" not in current_user.role_values:
        raise HTTPException(status_code=400, detail="A completed session can't be deleted")

    if session.status == "done" and session.points_awarded:
        reward = await get_setting_int(db, "session_points_reward", 200)
        teacher = (await db.execute(select(User).where(User.id == session.teacher_id))).scalars().first()
        await adjust_points(db, session.teacher_id, -reward, f"Session deleted: {session.title}")
        if teacher and teacher.invited_by_id:
            await adjust_points(db, teacher.invited_by_id, -reward, f"Teacher session deleted: {session.title}")

    await db.delete(session)
    await db.commit()
    return {"status": "deleted"}


# ── Teacher Applications (Ambassador/Admin Review) ──────────────

@router.get("/teacher-applications", response_model=list[TeacherApplicationOut])
async def my_teacher_applications(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ambassador),
):
    if "admin" in current_user.role_values:
        q = select(TeacherApplication)
    else:
        q = select(TeacherApplication).where(TeacherApplication.invited_by_id == current_user.id)
    if status:
        q = q.where(TeacherApplication.status == status)
    q = q.order_by(TeacherApplication.created_at.desc())
    rows = (await db.execute(q)).scalars().all()
    return rows


@router.get("/teacher-applications/{app_id}", response_model=TeacherApplicationOut)
async def get_my_teacher_application(
    app_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ambassador),
):
    if "admin" in current_user.role_values:
        q = select(TeacherApplication).where(TeacherApplication.id == app_id)
    else:
        q = select(TeacherApplication).where(
            TeacherApplication.id == app_id,
            TeacherApplication.invited_by_id == current_user.id
        )
    app = (await db.execute(q)).scalars().first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.put("/teacher-applications/{app_id}/approve", response_model=TeacherApplicationOut)
async def approve_teacher_application_ambassador(
    app_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ambassador),
):
    if "admin" in current_user.role_values:
        app = (await db.execute(
            select(TeacherApplication).where(TeacherApplication.id == app_id)
        )).scalars().first()
    else:
        app = (await db.execute(
            select(TeacherApplication).where(
                TeacherApplication.id == app_id,
                TeacherApplication.invited_by_id == current_user.id
            )
        )).scalars().first()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.status != "pending":
        raise HTTPException(status_code=400, detail="Application is not pending")

    user = User(
        full_name=app.full_name,
        email=app.email,
        password_hash=app.password_hash,
        roles=["teacher"],
        invited_by_id=app.invited_by_id,
        status="active",
    )
    db.add(user)
    app.status = "approved"

    # Reward recruiting ambassador
    if app.invited_by_id:
        reward = await get_setting_int(db, "teacher_points_reward", 500)
        await award_points(db, app.invited_by_id, reward, f"Recruited teacher: {app.full_name}")
        await notify(db, app.invited_by_id, "Points Earned!", f"You earned {reward} points for recruiting {app.full_name}.")
    await notify(db, user.id, "Application Approved", "Your teacher application was approved — welcome aboard!")

    await db.flush()
    if app.invited_by_id:
        await achievements.check_and_grant(db, app.invited_by_id)
    await db.commit()
    await db.refresh(app)
    return app


@router.put("/teacher-applications/{app_id}/reject", response_model=TeacherApplicationOut)
async def reject_teacher_application_ambassador(
    app_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ambassador),
):
    if "admin" in current_user.role_values:
        app = (await db.execute(
            select(TeacherApplication).where(TeacherApplication.id == app_id)
        )).scalars().first()
    else:
        app = (await db.execute(
            select(TeacherApplication).where(
                TeacherApplication.id == app_id,
                TeacherApplication.invited_by_id == current_user.id
            )
        )).scalars().first()

    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.status != "pending":
        raise HTTPException(status_code=400, detail="Application is not pending")

    app.status = "rejected"
    await db.commit()
    await db.refresh(app)
    return app
