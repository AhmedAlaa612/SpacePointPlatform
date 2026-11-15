"""Public application endpoints — no auth required."""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.apply_config import CONFIGURABLE_APPLY_ROLES, ROLES_REQUIRING_CODE, ROLES_WITH_CV, VALID_ROLES
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.application import Application
from app.models.application_question import ApplicationQuestion
from app.models.inventory.city import City
from app.models.user import User
from app.services.apply_form_config import (
    enforce_standard_field_requirements,
    get_hidden_question_ids,
    get_role_form_config,
    validate_and_snapshot_custom_questions,
)
from app.services.spine.identity import normalize_user_email, user_email_matches

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
    if role not in CONFIGURABLE_APPLY_ROLES:
        raise HTTPException(status_code=404, detail="Unknown role")
    rows = (await db.execute(
        select(ApplicationQuestion)
        .where(ApplicationQuestion.audience == role, ApplicationQuestion.is_active.is_(True))
        .order_by(ApplicationQuestion.sort_order, ApplicationQuestion.created_at)
    )).scalars().all()
    hidden_ids = await get_hidden_question_ids(db, role)
    return [_question_out(q) for q in rows if str(q.id) not in hidden_ids]


@router.get("/{role}/form-config")
async def get_public_apply_form_config(role: str, db: AsyncSession = Depends(get_db)):
    """Public: full form field visibility/requiredness + active custom questions for a role."""
    if role not in CONFIGURABLE_APPLY_ROLES:
        raise HTTPException(status_code=404, detail="Unknown role")
    return await get_role_form_config(db, role)


@router.post("/{role}", status_code=status.HTTP_201_CREATED)
async def submit_application(
    role: str,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    phone: Optional[str] = Form(None),
    country: Optional[str] = Form(None),
    city_id: Optional[str] = Form(None),
    city_other: Optional[str] = Form(None),
    invite_code: Optional[str] = Form(None),
    birthdate: Optional[str] = Form(None),
    nationality: Optional[str] = Form(None),
    answers: Optional[str] = Form(None),   # JSON string
    cv: Optional[UploadFile] = File(None),
    # Internship request fields (2026-08-20, role="intern" only) — collected
    # alongside the rest of the application, not a separate step. Stored
    # under fixed keys in `answers` (distinct from the freeform
    # ApplicationQuestion-driven answers, which are keyed by question id) so
    # routers/admin/applications.py can read them reliably by name — see
    # HANDOFF_INTERNSHIP.md.
    university: Optional[str] = Form(None),
    major: Optional[str] = Form(None),
    university_id_number: Optional[str] = Form(None),
    preferred_city_id: Optional[str] = Form(None),
    requested_start_date: Optional[str] = Form(None),
    requested_duration_weeks: Optional[int] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    import json
    if role not in VALID_ROLES:
        raise HTTPException(status_code=404, detail="Unknown role")

    form_config = await get_role_form_config(db, role)
    invite_cfg = next((f for f in form_config["fields"] if f["key"] == "invite_code"), None)
    invite_required = (
        bool(invite_cfg["enabled"] and invite_cfg["required"])
        if (form_config.get("has_custom_override") and invite_cfg)
        else (role in ROLES_REQUIRING_CODE)
    )
    if invite_required and not (invite_code and invite_code.strip()):
        raise HTTPException(status_code=400, detail="Invite code required for this role")

    # Canonical normalization at the write boundary (strip + lowercase) —
    # Application/User model validators enforce the same form; lookups are
    # case-insensitive so legacy rows can't slip past the duplicate check.
    email = normalize_user_email(email)

    # Unique email check across both users and pending applications
    existing_user = (await db.execute(select(User.id).where(user_email_matches(email)))).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    existing_app = (await db.execute(
        select(Application.id).where(func.lower(Application.email) == email, Application.status == "pending")
    )).first()
    if existing_app:
        raise HTTPException(status_code=400, detail="A pending application already exists for this email")

    # Resolve invite code → user
    invited_by_id = None
    if invite_code and invite_code.strip():
        code = invite_code.strip().upper()
        amb = (await db.execute(
            select(User).where(User.invite_code == code, User.status == "active")
        )).scalars().first()
        if amb:
            invited_by_id = amb.id
        elif invite_required:
            raise HTTPException(status_code=400, detail="Invalid or inactive invite code")

    parsed_answers: dict = {}
    if answers:
        try:
            loaded = json.loads(answers)
            if isinstance(loaded, dict):
                parsed_answers = loaded
        except Exception:
            pass
    if birthdate:
        parsed_answers["birthdate"] = birthdate
    if nationality and nationality.strip():
        parsed_answers["nationality"] = nationality.strip()
    if city_other:
        parsed_answers["city_other"] = city_other

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
                "university": university,
                "major": major,
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

    standard_values = {
        "phone": phone,
        "birthdate": parsed_answers.get("birthdate"),
        "nationality": parsed_answers.get("nationality"),
        "country": country,
        "city": city_id or parsed_answers.get("city_other") or parsed_answers.get("city"),
        "invite_code": invite_code,
        "cv": bool(cv and cv.filename),
        "university": parsed_answers.get("university"),
        "major": parsed_answers.get("major"),
        "university_id_number": parsed_answers.get("university_id_number"),
        "preferred_city_id": parsed_answers.get("preferred_city_id"),
        "requested_start_date": parsed_answers.get("requested_start_date"),
        "requested_duration_weeks": parsed_answers.get("requested_duration_weeks"),
    }
    enforce_standard_field_requirements(form_config, standard_values)

    parsed_answers, question_snapshots = await validate_and_snapshot_custom_questions(
        db, role, parsed_answers
    )
    if question_snapshots:
        parsed_answers["_question_snapshots"] = question_snapshots

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
        await notify(
            db,
            admin.id,
            f"New {role.title()} Application",
            f"{full_name} applied as {role}.",
            type="application",
            link=f"/admin/applications?id={app_id}",
        )

    await db.commit()
    return {"id": str(app_id), "status": "pending"}
