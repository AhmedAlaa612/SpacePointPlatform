"""Internship request/letter — top-level, not nested under routers/interns/
(the existing project-management kanban domain — teams/epics/tasks, a
different bounded context that just happens to share the word "intern") or
routers/instructors/ (would wrongly imply instructors own this domain just
because they're the only role allowed to request it today). Same mounting
pattern as routers/documents.py and routers/apply.py.

Three surfaces:
- POST /me/role-requests — any authenticated user requests an additional
  role, gated by services/internship/allowed_role_requests.py's allowlist.
  Generic on purpose (2026-08-20 operator ask) — not intern-specific.
- /admin/role-requests/* — admin review queue + approve/reject. Approval's
  actual side effect (create InternProfile + generate the letter) is
  dispatched by target_role; today only "intern" has a handler
  (services/internship/approval.py).
- /intern/internship-letter/* — the intern's own view of their letter +
  in-app signing, mirrors routers/instructors/instructor.py's contract
  endpoints exactly.
"""

import asyncio
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import get_current_active_user, require_admin, require_intern
from app.db.session import get_db
from app.models.enums import ApplicationStatus, UserRole
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.application_review import ApplicationReview
from app.models.instructors.video_submission import VideoSubmission
from app.models.internship import InternProfile, RoleRequest
from app.models.user import User
from app.schemas.internship import (
    InternProfileOut,
    InternshipApprove,
    InternshipIntakeEligibilityOut,
    InternshipPreviewRequest,
    RoleRequestCreate,
    RoleRequestOut,
    RoleRequestReject,
    SignInternshipLetterRequest,
    StudentInternApply,
)
from app.services import storage
from app.services.documents.internship_letter import generate_internship_letter_pdf
from app.services.email import (
    send_internship_letter_signed_notification_email,
    send_signed_internship_letter_email,
)
from app.services.instructors.application_videos import get_configured_videos
from app.services.instructors.deadlines import (
    compute_phase_deadline,
    get_instructor_settings,
    is_student_eligible_for_internship,
)
from app.services.internship.allowed_role_requests import can_request_role
from app.services.internship.approval import approve_internship, format_letter_date, resolve_internship_request_fields, resolve_start_date
from app.services.internship.ref_number import peek_next_ref_number
from app.services.notification import create_notification as notify

router = APIRouter(tags=["internship"])


# ── target_role-specific `details` validation ───────────────────────────────
# Only "intern" exists today; add a sibling function + dispatch entry for a
# future target_role rather than a generic freeform validator.

def _validate_intern_details(details: dict) -> dict:
    allowed_keys = {
        "university",
        "university_id_number",
        "preferred_city_id",
        "requested_start_date",
        "requested_duration_weeks",
        "major",
        "cv_path",
        "cv_url",
    }
    unknown = set(details) - allowed_keys
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown fields: {sorted(unknown)}")
    if details.get("requested_start_date"):
        try:
            date.fromisoformat(details["requested_start_date"])
        except ValueError:
            raise HTTPException(status_code=400, detail="requested_start_date must be YYYY-MM-DD")
    if details.get("preferred_city_id"):
        try:
            uuid.UUID(str(details["preferred_city_id"]))
        except ValueError:
            raise HTTPException(status_code=400, detail="preferred_city_id must be a valid city id")
    return details


_DETAILS_VALIDATORS = {"intern": _validate_intern_details}


# ── self-apply ───────────────────────────────────────────────────────────────

@router.post("/me/role-requests", response_model=RoleRequestOut, status_code=201)
async def create_role_request(
    body: RoleRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if not can_request_role(current_user.role_values, body.target_role):
        raise HTTPException(status_code=403, detail=f"Your role cannot request '{body.target_role}'")
    if body.target_role in current_user.role_values:
        raise HTTPException(status_code=400, detail=f"You already hold the '{body.target_role}' role")

    existing = (await db.execute(
        select(RoleRequest).where(
            RoleRequest.requester_user_id == current_user.id,
            RoleRequest.target_role == body.target_role,
            RoleRequest.status == "pending",
        )
    )).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="A pending request for this role already exists")

    validator = _DETAILS_VALIDATORS.get(body.target_role)
    details = validator(body.details) if validator else body.details

    req = RoleRequest(requester_user_id=current_user.id, target_role=body.target_role, details=details)
    db.add(req)

    admins = (await db.execute(select(User).where(User.roles.any("admin")))).scalars().all()
    for admin in admins:
        await notify(db, admin.id, "New Role Request",
                     f"{current_user.full_name} requested the '{body.target_role}' role.", type="role_request")

    await db.commit()
    await db.refresh(req)
    return _request_out(req, current_user)


@router.get("/me/role-requests", response_model=list[RoleRequestOut])
async def list_my_role_requests(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    rows = (await db.execute(
        select(RoleRequest).where(RoleRequest.requester_user_id == current_user.id).order_by(RoleRequest.created_at.desc())
    )).scalars().all()
    return [_request_out(r, current_user) for r in rows]


@router.get("/internship/intake-eligibility", response_model=InternshipIntakeEligibilityOut)
async def get_internship_intake_eligibility(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Checks whether the currently authenticated student is eligible to apply for an internship."""
    settings = await get_instructor_settings(db)
    pending_req = (await db.execute(
        select(RoleRequest).where(
            RoleRequest.requester_user_id == current_user.id,
            RoleRequest.target_role == "intern",
            RoleRequest.status == "pending",
        )
    )).scalars().first()

    eligible, reason = is_student_eligible_for_internship(
        current_user, settings, has_pending_request=bool(pending_req)
    )
    university_name = None
    if current_user.organization_id:
        from app.models.spine.organization import Organization
        org = await db.get(Organization, current_user.organization_id)
        if org:
            university_name = org.name_latin

    return InternshipIntakeEligibilityOut(
        eligible=eligible,
        reason=reason,
        has_birthdate=bool(current_user.birthdate),
        has_pending_request=bool(pending_req),
        min_age=settings.get("internship_intake_min_age", 18),
        university=university_name,
        student_id=current_user.student_id,
    )


@router.post("/internship/apply-as-student", response_model=RoleRequestOut, status_code=201)
async def apply_as_student_for_internship(
    payload_json: str = Form(..., alias="payload"),
    cv: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Authenticated student application for an internship role."""
    settings = await get_instructor_settings(db)
    pending_req = (await db.execute(
        select(RoleRequest).where(
            RoleRequest.requester_user_id == current_user.id,
            RoleRequest.target_role == "intern",
            RoleRequest.status == "pending",
        )
    )).scalars().first()

    eligible, reason = is_student_eligible_for_internship(
        current_user, settings, has_pending_request=bool(pending_req)
    )
    if not eligible:
        raise HTTPException(status_code=400, detail=reason or "Not eligible to apply for internship")

    try:
        payload = StudentInternApply.model_validate_json(payload_json)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid application payload")

    if not payload.university or not payload.university.strip():
        raise HTTPException(status_code=400, detail="University name is required")
    if not payload.university_id_number or not payload.university_id_number.strip():
        raise HTTPException(status_code=400, detail="University / Student ID is required")

    # Profile sync: save university and student ID back to User record (and prefill vice versa)
    if payload.university and payload.university.strip():
        from app.services.spine.identity import resolve_or_create_organization
        org_row = await resolve_or_create_organization(db, payload.university.strip(), org_type="university")
        current_user.organization_id = org_row.id
        if current_user.contact_id:
            from app.models.spine.contact import Contact
            c_row = await db.get(Contact, current_user.contact_id)
            if c_row:
                c_row.organization_id = org_row.id

    current_user.student_id = payload.university_id_number.strip()

    # CV upload
    cv_path = None
    cv_url = None
    if cv and cv.filename:
        ext = ("." + cv.filename.rsplit(".", 1)[-1].lower()) if "." in cv.filename else ""
        if ext not in [".pdf", ".doc", ".docx"]:
            raise HTTPException(status_code=400, detail="CV must be a PDF or Word document (.pdf, .doc, .docx)")
        cv_path = f"intern/{current_user.id}{ext}"
        cv_url = await storage.upload_file("cvs", cv_path, await cv.read(), cv.content_type or "application/pdf")

    details = {
        "university": payload.university.strip(),
        "university_id_number": payload.university_id_number.strip(),
        "preferred_city_id": str(payload.preferred_city_id) if payload.preferred_city_id else None,
        "requested_start_date": payload.requested_start_date,
        "requested_duration_weeks": payload.requested_duration_weeks or 8,
        "major": payload.major,
        "cv_path": cv_path,
        "cv_url": cv_url,
    }

    req = RoleRequest(
        requester_user_id=current_user.id,
        target_role="intern",
        status="pending",
        details=details,
    )
    db.add(req)

    admins = (await db.execute(select(User).where(User.roles.any("admin")))).scalars().all()
    for admin in admins:
        await notify(
            db, admin.id, "New Intern Application",
            f"{current_user.full_name} applied for an internship.", type="role_request"
        )

    await db.commit()
    await db.refresh(req)
    await db.refresh(current_user)
    return _request_out(req, current_user)


def _request_out(req: RoleRequest, requester: User) -> RoleRequestOut:
    return RoleRequestOut(
        id=req.id, requester_user_id=req.requester_user_id,
        requester_name=requester.full_name, requester_email=requester.email,
        target_role=req.target_role, status=req.status, details=req.details or {},
        resolution=req.resolution or {}, admin_notes=req.admin_notes,
        reviewed_by=req.reviewed_by, reviewed_at=req.reviewed_at, created_at=req.created_at,
    )


# ── admin review ─────────────────────────────────────────────────────────────

@router.post("/admin/internship-letter/preview")
async def preview_internship_letter(
    body: InternshipPreviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Renders the letter exactly as the real approve/onboard actions would,
    from whatever the admin has typed into the form so far — no DB writes,
    no ref number consumed, no email sent. Lets an admin sanity-check the
    letter before committing to Approve."""
    approval_date = datetime.now(timezone.utc).date()
    start_date = resolve_start_date(body.requested_start_date, body.start_date_override, approval_date)
    ref_number = await peek_next_ref_number(db, override=body.ref_number_override)
    supervisor_first_name = body.supervisor_name.split(" ")[0] if body.supervisor_name else ""
    # Same "admin override wins, else fall back to what was requested"
    # rule resolve_internship_request_fields applies for the real approve
    # flow — the preview form doesn't always have duration_weeks typed in
    # yet (it comes from the applicant's own request instead), same as the
    # real letter wouldn't.
    duration_weeks = body.duration_weeks if body.duration_weeks is not None else body.requested_duration_weeks

    pdf_bytes = await asyncio.to_thread(
        generate_internship_letter_pdf,
        ref_number=ref_number,
        university_id=body.university_id_number or "",
        letter_date=format_letter_date(approval_date),
        salutation=body.salutation,
        intern_name=body.intern_name,
        start_date=format_letter_date(start_date) if start_date else format_letter_date(approval_date),
        duration_weeks=duration_weeks or 0,
        activity_description=body.activity_description,
        hours_per_week=body.hours_per_week or 0,
        supervisor_title=body.supervisor_title,
        supervisor_name=body.supervisor_name,
        supervisor_first_name=supervisor_first_name,
        supervisor_email=body.supervisor_email,
        supervisor_phone=body.supervisor_phone,
    )
    return Response(content=pdf_bytes, media_type="application/pdf")


@router.get("/admin/role-requests", response_model=list[RoleRequestOut])
async def list_role_requests(
    status: str | None = Query(None),
    target_role: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    stmt = select(RoleRequest, User).join(User, User.id == RoleRequest.requester_user_id)
    if status:
        stmt = stmt.where(RoleRequest.status == status)
    if target_role:
        stmt = stmt.where(RoleRequest.target_role == target_role)
    stmt = stmt.order_by(RoleRequest.created_at.desc())
    rows = (await db.execute(stmt)).all()
    return [_request_out(req, requester) for req, requester in rows]


async def _get_pending_request(db: AsyncSession, req_id: uuid.UUID) -> RoleRequest:
    req = await db.get(RoleRequest, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {req.status}")
    return req


@router.post("/admin/role-requests/{req_id}/approve", response_model=RoleRequestOut)
async def approve_role_request(
    req_id: uuid.UUID,
    body: InternshipApprove,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    req = await _get_pending_request(db, req_id)
    if req.target_role != "intern":
        raise HTTPException(status_code=400, detail=f"No approval handler for target_role '{req.target_role}'")

    user = await db.get(User, req.requester_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Requester account not found")

    details = req.details or {}
    university_id_number, start_date = resolve_internship_request_fields(body, details)

    profile = await approve_internship(
        db, user=user,
        university_id_number=university_id_number,
        start_date=start_date, department=None, approve=body,
    )

    # Role hygiene on approval: if user was a student, strip student so they become clean [intern]
    kept = {r for r in user.role_values if r != UserRole.student.value}
    kept.add(UserRole.intern.value)
    user.roles = [UserRole(r) for r in sorted(kept)]

    req.status = "approved"
    req.resolution = {
        "final_city_id": str(body.city_id) if body.city_id else None,
        "final_duration_weeks": body.duration_weeks,
        "final_hours_per_week": body.hours_per_week,
        "supervisor_name": body.supervisor_name,
        "supervisor_email": body.supervisor_email,
        "supervisor_phone": body.supervisor_phone,
        "ref_number": profile.ref_number,
        "letter_date": datetime.now(timezone.utc).date().isoformat(),
    }
    req.admin_notes = body.admin_notes
    req.reviewed_by = current_user.id
    req.reviewed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(req)
    return _request_out(req, user)


@router.post("/admin/role-requests/{req_id}/onboard-to-instructor", response_model=RoleRequestOut)
async def onboard_role_request_to_instructor(
    req_id: uuid.UUID,
    body: InternshipApprove,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Route a pending intern role request into the instructor onboarding pipeline.
    Completing that pipeline grants both [instructor, intern] roles and auto-generates the internship letter.
    During onboarding, the student holds [applicant, student]."""
    req = await _get_pending_request(db, req_id)
    if req.target_role != "intern":
        raise HTTPException(status_code=400, detail="Only intern role requests can be routed to onboarding")

    user = await db.get(User, req.requester_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Requester account not found")

    details = req.details or {}
    university_id_number, start_date = resolve_internship_request_fields(body, details)
    pending_intern_details = {
        "university_id_number": university_id_number,
        "start_date": start_date.isoformat() if start_date else None,
        "approve": body.model_dump(mode="json"),
    }

    profile = await db.get(ApplicantProfile, user.id)
    if profile is None:
        profile = ApplicantProfile(
            user_id=user.id,
            university=details.get("university") or user.organization_name,
            cv_path=details.get("cv_path"),
            also_grant_role="intern",
            pending_intern_details=pending_intern_details,
        )
        db.add(profile)
    else:
        profile.also_grant_role = "intern"
        profile.pending_intern_details = pending_intern_details
        if details.get("cv_path"):
            profile.cv_path = details.get("cv_path")

    # Seed video submissions if needed
    for v in await get_configured_videos(db):
        existing_v = (await db.execute(
            select(VideoSubmission).where(
                VideoSubmission.user_id == user.id,
                VideoSubmission.video_no == v["video_no"],
            )
        )).scalars().first()
        if not existing_v:
            db.add(VideoSubmission(user_id=user.id, video_no=v["video_no"], youtube_url=v["url"]))

    # Seed application review with phase 1 deadline
    inst_settings = await get_instructor_settings(db)
    deadline = compute_phase_deadline(inst_settings["instructor_deadline_phase1_days"])
    now = datetime.now(timezone.utc)

    review = (await db.execute(
        select(ApplicationReview).where(ApplicationReview.user_id == user.id)
    )).scalars().first()
    if review is None:
        db.add(ApplicationReview(
            user_id=user.id,
            status=ApplicationStatus.in_progress,
            phase_deadline=deadline,
            extension_used=False,
            created_at=now,
            last_status_change_at=now,
        ))
    else:
        review.status = ApplicationStatus.in_progress
        review.reviewed_at = None
        review.admin_id = None
        review.feedback = None
        review.phase_deadline = deadline
        review.extension_used = False
        review.last_status_change_at = now

    # Grant applicant role alongside existing student role: [applicant, student]
    current_roles = [r.value if hasattr(r, "value") else str(r) for r in (user.roles or [])]
    if "applicant" not in current_roles:
        current_roles.append("applicant")
    user.roles = [UserRole(r) for r in current_roles]

    req.status = "approved"
    req.admin_notes = body.admin_notes or "Routed to Instructor Onboarding"
    req.reviewed_by = current_user.id
    req.reviewed_at = now
    req.resolution = {
        "routed_to_onboarding": True,
        "decision": "onboard-to-instructor",
        "letter_date": now.date().isoformat(),
    }

    await db.commit()
    await db.refresh(req)
    return _request_out(req, user)


@router.get("/admin/role-requests/{req_id}/cv-url")
async def get_role_request_cv_url(
    req_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    req = await db.get(RoleRequest, req_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    details = req.details or {}
    cv_path = details.get("cv_path")
    if cv_path:
        try:
            url = await storage.get_signed_url("cvs", cv_path)
            return {"cv_url": url}
        except Exception:
            pass
    if details.get("cv_url"):
        return {"cv_url": details["cv_url"]}
    raise HTTPException(status_code=404, detail="No CV found for this request")


@router.post("/admin/role-requests/{req_id}/reject", response_model=RoleRequestOut)
async def reject_role_request(
    req_id: uuid.UUID,
    body: RoleRequestReject,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    req = await _get_pending_request(db, req_id)
    user = await db.get(User, req.requester_user_id)

    req.status = "rejected"
    req.admin_notes = body.admin_notes
    req.reviewed_by = current_user.id
    req.reviewed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(req)
    return _request_out(req, user)


# ── intern's own letter ──────────────────────────────────────────────────────

async def _profile_out(profile: InternProfile) -> InternProfileOut:
    return InternProfileOut(
        user_id=profile.user_id, ref_number=profile.ref_number,
        university_id_number=profile.university_id_number, department=profile.department,
        start_date=profile.start_date, duration_weeks=profile.duration_weeks,
        hours_per_week=profile.hours_per_week, work_city_id=profile.work_city_id,
        supervisor_name=profile.supervisor_name, supervisor_email=profile.supervisor_email,
        supervisor_phone=profile.supervisor_phone,
        letter_url=await storage.resolve_url("internship-letters", profile.letter_path, None) if profile.letter_path else None,
        signed_letter_url=await storage.resolve_url("internship-letters", profile.signed_letter_path, None) if profile.signed_letter_path else None,
        letter_signed_at=profile.letter_signed_at,
    )


@router.get("/intern/internship-letter", response_model=InternProfileOut | None)
async def get_my_internship_letter(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_intern)):
    profile = await db.get(InternProfile, current_user.id)
    if not profile:
        return None
    return await _profile_out(profile)


@router.post("/intern/internship-letter/sign", response_model=InternProfileOut)
async def sign_internship_letter(
    body: SignInternshipLetterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_intern),
):
    profile = await db.get(InternProfile, current_user.id)
    if not profile or not profile.letter_path:
        raise HTTPException(status_code=404, detail="No internship letter on file to sign")
    if profile.letter_signed_at:
        raise HTTPException(status_code=400, detail="Internship letter already signed")

    # `letter_date` (the printed Date: field) is frozen at approval time —
    # never recomputed here, same reasoning as contract.py's instructor_since.
    letter_date = f"{profile.letter_date.day} {profile.letter_date.strftime('%B %Y')}" if profile.letter_date else ""
    start_date_str = f"{profile.start_date.day} {profile.start_date.strftime('%B %Y')}" if profile.start_date else letter_date
    try:
        pdf_bytes = await asyncio.to_thread(
            generate_internship_letter_pdf,
            ref_number=profile.ref_number or "", university_id=profile.university_id_number or "",
            letter_date=letter_date, salutation=profile.salutation or "", intern_name=current_user.full_name,
            start_date=start_date_str, duration_weeks=profile.duration_weeks or 0,
            activity_description=profile.department or "", hours_per_week=profile.hours_per_week or 0,
            supervisor_title=profile.supervisor_title or "", supervisor_name=profile.supervisor_name or "",
            supervisor_first_name=(profile.supervisor_name or "").split(" ")[0],
            supervisor_email=profile.supervisor_email or "", supervisor_phone=profile.supervisor_phone or "",
            intern_signature_b64=body.signature,
        )
        signed_path = f"{current_user.id}/internship_letter_signed.pdf"
        await storage.upload_file("internship-letters", signed_path, pdf_bytes, "application/pdf")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Signed letter generation or upload failed: {str(e)}")

    profile.signed_letter_path = signed_path
    profile.letter_signature_data = body.signature
    profile.letter_signed_at = datetime.now(timezone.utc)

    admins = (await db.execute(select(User).where(User.roles.any("admin")))).scalars().all()
    for admin in admins:
        await notify(db, admin.id, "Internship Letter Signed",
                     f"{current_user.full_name} signed their internship letter.", type="internship")
        await send_internship_letter_signed_notification_email(admin.email, current_user.full_name)
    await send_signed_internship_letter_email(current_user.email, current_user.full_name, pdf_bytes)

    await db.commit()
    await db.refresh(profile)
    return await _profile_out(profile)
