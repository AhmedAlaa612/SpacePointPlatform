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

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import get_current_active_user, require_admin, require_intern
from app.db.session import get_db
from app.models.internship import InternProfile, RoleRequest
from app.models.user import User
from app.schemas.internship import (
    InternProfileOut,
    InternshipApprove,
    RoleRequestCreate,
    RoleRequestOut,
    RoleRequestReject,
    SignInternshipLetterRequest,
)
from app.services import storage
from app.services.documents.internship_letter import generate_internship_letter_pdf
from app.services.email import (
    send_internship_letter_signed_notification_email,
    send_signed_internship_letter_email,
)
from app.services.internship.allowed_role_requests import can_request_role
from app.services.internship.approval import approve_internship, resolve_internship_request_fields
from app.services.notification import create_notification as notify

router = APIRouter(tags=["internship"])


# ── target_role-specific `details` validation ───────────────────────────────
# Only "intern" exists today; add a sibling function + dispatch entry for a
# future target_role rather than a generic freeform validator.

def _validate_intern_details(details: dict) -> dict:
    allowed_keys = {"university_id_number", "preferred_city_id", "requested_start_date", "requested_duration_weeks"}
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


def _request_out(req: RoleRequest, requester: User) -> RoleRequestOut:
    return RoleRequestOut(
        id=req.id, requester_user_id=req.requester_user_id,
        requester_name=requester.full_name, requester_email=requester.email,
        target_role=req.target_role, status=req.status, details=req.details or {},
        resolution=req.resolution or {}, admin_notes=req.admin_notes,
        reviewed_by=req.reviewed_by, reviewed_at=req.reviewed_at, created_at=req.created_at,
    )


# ── admin review ─────────────────────────────────────────────────────────────

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
