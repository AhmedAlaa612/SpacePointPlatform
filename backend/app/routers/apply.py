"""Public application endpoints — no auth required."""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.application import Application
from app.models.inventory.city import City
from app.core.apply_config import ROLES_REQUIRING_CODE, ROLES_WITH_CV, VALID_ROLES
from app.models.application_question import ApplicationQuestion
from app.models.user import User

router = APIRouter(prefix="/apply", tags=["apply"])


def _question_out(q: ApplicationQuestion) -> dict:
    return {
        "id": str(q.id),
        "question_text": q.question_text,
        "question_type": q.question_type,
        "required": q.required,
        "order": q.sort_order,
        "options": q.options or [],
    }


@router.get("/{role}/questions")
async def list_apply_questions(role: str, db: AsyncSession = Depends(get_db)):
    """Public: active custom questions for a role's apply form."""
    if role not in VALID_ROLES:
        raise HTTPException(status_code=404, detail="Unknown role")
    rows = (await db.execute(
        select(ApplicationQuestion)
        .where(ApplicationQuestion.audience == role, ApplicationQuestion.is_active.is_(True))
        .order_by(ApplicationQuestion.sort_order, ApplicationQuestion.created_at)
    )).scalars().all()
    return [_question_out(q) for q in rows]


@router.post("/{role}", status_code=status.HTTP_201_CREATED)
async def submit_application(
    role: str,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    phone: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    city_id: Optional[str] = Form(None),
    invite_code: Optional[str] = Form(None),
    answers: Optional[str] = Form(None),   # JSON string
    cv: Optional[UploadFile] = File(None),
    # Internship request fields (2026-08-20, role="intern" only) — collected
    # alongside the rest of the application, not a separate step. Stored
    # under fixed keys in `answers` (distinct from the freeform
    # ApplicationQuestion-driven answers, which are keyed by question id) so
    # routers/admin/applications.py can read them reliably by name — see
    # HANDOFF_INTERNSHIP.md.
    university_id_number: Optional[str] = Form(None),
    preferred_city_id: Optional[str] = Form(None),
    requested_start_date: Optional[str] = Form(None),
    requested_duration_weeks: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    import json
    if role not in VALID_ROLES:
        raise HTTPException(status_code=404, detail="Unknown role")
    if role in ROLES_REQUIRING_CODE and not invite_code:
        raise HTTPException(status_code=400, detail="Invite code required for this role")

    # Lowercase at the write boundary, same as /auth/login and /auth/signup
    # (services/spine/identity.py::normalize_email is the canonical form) —
    # otherwise a mixed-case email stored here can never log in later.
    email = email.strip().lower()

    # Unique email check across both users and pending applications
    existing_user = (await db.execute(select(User.id).where(User.email == email))).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    existing_app = (await db.execute(
        select(Application.id).where(Application.email == email, Application.status == "pending")
    )).first()
    if existing_app:
        raise HTTPException(status_code=400, detail="A pending application already exists for this email")

    # Resolve invite code → user
    invited_by_id = None
    if invite_code:
        code = invite_code.strip().upper()
        amb = (await db.execute(
            select(User).where(User.invite_code == code, User.status == "active")
        )).scalars().first()
        if amb:
            invited_by_id = amb.id
        elif role in ROLES_REQUIRING_CODE:
            raise HTTPException(status_code=400, detail="Invalid or inactive invite code")

    # CV upload
    app_id = uuid.uuid4()
    cv_url = None
    cv_path = None
    if cv and cv.filename:
        from app.services import storage
        ext = ("." + cv.filename.rsplit(".", 1)[-1]) if "." in cv.filename else ""
        data = await cv.read()
        cv_path = f"{role}/{app_id}{ext}"
        cv_url = await storage.upload_file("cvs", cv_path, data, cv.content_type or "application/pdf")

    parsed_answers = {}
    if answers:
        try:
            parsed_answers = json.loads(answers)
        except Exception:
            pass

    if role == "intern":
        if preferred_city_id:
            try:
                uuid.UUID(preferred_city_id)
            except ValueError:
                raise HTTPException(status_code=400, detail="Unknown preferred city")
        if requested_start_date:
            try:
                date.fromisoformat(requested_start_date)
            except ValueError:
                raise HTTPException(status_code=400, detail="requested_start_date must be YYYY-MM-DD")
        parsed_answers.update({
            k: v for k, v in {
                "university_id_number": university_id_number,
                "preferred_city_id": preferred_city_id,
                "requested_start_date": requested_start_date,
                "requested_duration_weeks": requested_duration_weeks,
            }.items() if v is not None
        })

    # City (2026-08-08) — optional and validated like auth signup does: the
    # apply form only offers cities in the chosen (mobile) country, so an
    # unknown id means the client is out of sync, not a soft ignore.
    if city_id:
        try:
            city_uuid = uuid.UUID(city_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Unknown city")
        city = await db.get(City, city_uuid)
        if not city:
            raise HTTPException(status_code=400, detail="Unknown city")
    else:
        city_uuid = None

    app = Application(
        id=app_id,
        role=role,
        full_name=full_name,
        email=email,
        phone=phone,
        country=country,
        city_id=city_uuid,
        password_hash=get_password_hash(password),
        invite_code=invite_code,
        invited_by_id=invited_by_id,
        cv_url=cv_url,
        cv_path=cv_path,
        answers=parsed_answers,
    )
    db.add(app)

    # Notify admins
    from app.services.notification import create_notification as notify
    admins = (await db.execute(select(User).where(User.roles.any("admin")))).scalars().all()
    for admin in admins:
        await notify(db, admin.id, f"New {role.title()} Application",
                     f"{full_name} applied as {role}.", type="application")

    await db.commit()
    return {"id": str(app_id), "status": "pending"}
