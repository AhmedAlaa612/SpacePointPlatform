"""Admin: manage applications."""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.application import Application
from app.models.application_question import ApplicationQuestion
from app.models.enums import UserRole
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.application_review import ApplicationReview
from app.models.user import User
from app.services import storage
from app.services.email import send_application_approved_email, send_moved_to_onboarding_email
from app.services.notification import create_notification as notify
from app.services.points import award_points, get_setting_int

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ReviewBody(BaseModel):
    admin_notes: Optional[str] = None


# ── Applications ──────────────────────────────────────────────────────────────

@router.get("/applications")
async def list_applications(
    role: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    q = select(Application).order_by(Application.created_at.desc())
    if role:
        q = q.where(Application.role == role)
    if status:
        q = q.where(Application.status == status)
    rows = (await db.execute(q)).scalars().all()
    return [_app_out(a) for a in rows]


@router.get("/applications/counts")
async def application_counts(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    rows = (await db.execute(
        select(Application.role, Application.status, func.count().label("n"))
        .group_by(Application.role, Application.status)
    )).all()
    result: dict = {}
    for role, status, n in rows:
        result.setdefault(role, {})
        result[role][status] = n
    return result


@router.get("/applications/{app_id}")
async def get_application(
    app_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    app = (await db.execute(select(Application).where(Application.id == app_id))).scalars().first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    out = _app_out(app)
    cv_path = app.cv_path or (_path_from_url(app.cv_url) if app.cv_url else None)
    if cv_path:
        try:
            out["cv_signed_url"] = await storage.get_signed_url("cvs", cv_path)
        except Exception:
            out["cv_signed_url"] = app.cv_url
    return out


@router.post("/applications/{app_id}/approve")
async def approve_application(
    app_id: uuid.UUID,
    body: ReviewBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    app = await _get_pending(db, app_id)

    # Create the user
    from app.models.enums import UserRole
    role_map = {
        "ambassador": UserRole.ambassador,
        "intern":     UserRole.intern,
        "teacher":    UserRole.teacher,
        "facilitator": UserRole.facilitator,
    }
    user_role = role_map.get(app.role)
    if not user_role:
        raise HTTPException(status_code=400, detail="Unsupported role")

    import secrets
    new_user = User(
        full_name=app.full_name,
        email=app.email,
        password_hash=app.password_hash,
        phone=app.phone,
        country=app.country,
        roles=[user_role],
        status="active",
        invite_code=secrets.token_hex(4).upper(),
        invited_by_id=app.invited_by_id,
    )
    db.add(new_user)
    await db.flush()

    # Ambassador teacher-referral points — admin approval is now the single
    # canonical award point (was previously the ambassador-side approval).
    if app.role == "teacher" and app.invited_by_id:
        reward = await get_setting_int(db, "teacher_points_reward", 500)
        await award_points(db, app.invited_by_id, reward, f"Referred teacher {app.full_name} approved")

    # Mark application done
    app.status = "approved"
    app.admin_notes = body.admin_notes
    app.reviewed_by = current_user.id
    app.reviewed_at = datetime.now(timezone.utc)

    # Notify user
    await notify(db, new_user.id, "Application Approved",
                 f"Your {app.role} application has been approved. Welcome to SpacePoint!", type="application")

    email_sent = await send_application_approved_email(new_user.email, new_user.full_name, app.role)

    await db.commit()
    return {"detail": "approved", "user_id": str(new_user.id), "email_sent": email_sent}


@router.post("/applications/{app_id}/reject")
async def reject_application(
    app_id: uuid.UUID,
    body: ReviewBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    app = await _get_pending(db, app_id)
    app.status = "rejected"
    app.admin_notes = body.admin_notes
    app.reviewed_by = current_user.id
    app.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"detail": "rejected"}


@router.post("/applications/{app_id}/onboard")
async def onboard_application(
    app_id: uuid.UUID,
    body: ReviewBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Route a pending intern application into the instructor onboarding
    pipeline instead of accepting it directly. Completing that pipeline
    grants both the instructor and intern roles (see review_applicant() in
    routers/instructors/admin.py)."""
    app = await _get_pending(db, app_id)
    if app.role != "intern":
        raise HTTPException(status_code=400, detail="Only intern applications can be sent to onboarding")

    import secrets
    new_user = User(
        full_name=app.full_name,
        email=app.email,
        password_hash=app.password_hash,
        phone=app.phone,
        country=app.country,
        roles=[UserRole.applicant],
        status="active",
        invite_code=secrets.token_hex(4).upper(),
        invited_by_id=app.invited_by_id,
    )
    db.add(new_user)
    await db.flush()

    db.add(ApplicantProfile(
        user_id=new_user.id,
        cv_path=app.cv_path,
        country=app.country or "United Arab Emirates",
        also_grant_role="intern",
    ))
    db.add(ApplicationReview(user_id=new_user.id))

    app.status = "onboarding"
    app.admin_notes = body.admin_notes
    app.reviewed_by = current_user.id
    app.reviewed_at = datetime.now(timezone.utc)

    email_sent = await send_moved_to_onboarding_email(new_user.email, new_user.full_name)

    await db.commit()
    return {"detail": "onboarding", "user_id": str(new_user.id), "email_sent": email_sent}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _app_out(a: Application) -> dict:
    return {
        "id": str(a.id), "role": a.role, "status": a.status,
        "full_name": a.full_name, "email": a.email,
        "phone": a.phone, "country": a.country,
        "invite_code": a.invite_code,
        "has_cv": bool(a.cv_path or a.cv_url),
        "answers": a.answers,
        "admin_notes": a.admin_notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
    }


def _path_from_url(url: str) -> str:
    """Extract the storage path from a signed URL."""
    import re
    m = re.search(r"/object/(?:sign|public)/cvs/(.+?)(?:\?|$)", url)
    return m.group(1) if m else url


async def _get_pending(db, app_id: uuid.UUID) -> Application:
    app = (await db.execute(select(Application).where(Application.id == app_id))).scalars().first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    if app.status != "pending":
        raise HTTPException(status_code=400, detail=f"Application already {app.status}")
    return app


# ── Apply questions (admin-managed custom form per role) ──────────────────────

class QuestionBody(BaseModel):
    audience: str
    question_text: str
    question_type: str = "text"
    required: bool = True
    options: list[str] = []


class QuestionUpdate(BaseModel):
    audience: Optional[str] = None
    question_text: Optional[str] = None
    question_type: Optional[str] = None
    required: Optional[bool] = None
    options: Optional[list[str]] = None
    sort_order: Optional[int] = None


def _question_out(q: ApplicationQuestion) -> dict:
    return {
        "id": str(q.id), "question_text": q.question_text,
        "question_type": q.question_type, "required": q.required,
        "order": q.sort_order, "options": q.options or [],
    }


@router.get("/applications/questions/list")
async def list_questions(audience: str, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    rows = (await db.execute(
        select(ApplicationQuestion)
        .where(ApplicationQuestion.audience == audience, ApplicationQuestion.is_active.is_(True))
        .order_by(ApplicationQuestion.sort_order, ApplicationQuestion.created_at)
    )).scalars().all()
    return [_question_out(q) for q in rows]


@router.post("/applications/questions")
async def create_question(body: QuestionBody, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    max_order = (await db.execute(
        select(func.coalesce(func.max(ApplicationQuestion.sort_order), 0))
        .where(ApplicationQuestion.audience == body.audience)
    )).scalar() or 0
    q = ApplicationQuestion(
        audience=body.audience, question_text=body.question_text,
        question_type=body.question_type, required=body.required,
        options=body.options, sort_order=max_order + 1,
    )
    db.add(q)
    await db.commit()
    await db.refresh(q)
    return _question_out(q)


@router.patch("/applications/questions/{qid}")
async def update_question(
    qid: uuid.UUID, body: QuestionUpdate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)
):
    q = (await db.execute(select(ApplicationQuestion).where(ApplicationQuestion.id == qid))).scalars().first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(q, field, val)
    await db.commit()
    await db.refresh(q)
    return _question_out(q)


@router.delete("/applications/questions/{qid}")
async def delete_question(qid: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    q = (await db.execute(select(ApplicationQuestion).where(ApplicationQuestion.id == qid))).scalars().first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    q.is_active = False  # soft-delete; keeps historical answer references intact
    await db.commit()
    return {"detail": "deleted"}
