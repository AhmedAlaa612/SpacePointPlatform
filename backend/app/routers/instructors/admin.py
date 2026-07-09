import asyncio
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_admin
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.enums import ApplicationStatus, ModuleSubmissionStatus, UserRole
from sqlalchemy import func

from app.models.certificate import Certificate
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.application_review import ApplicationReview
from app.models.instructors.checklist import ChecklistModule
from app.models.instructors.instructor_document import InstructorDocument
from app.models.instructors.checklist import ModuleSection
from app.models.instructors.instructor_profile import InstructorProfile
from app.models.instructors.invitation_code import InvitationCode
from app.models.instructors.module_submission import ModuleSubmission
from app.models.instructors.payment import PaymentLetter, PortalSetting
from app.models.instructors.assessment_submission import AssessmentSubmission
from app.models.instructors.presentation_submission import PresentationSubmission
from app.models.instructors.video_submission import VideoSubmission
from app.models.user import User
from app.schemas.instructors.admin import (
    AdminOverviewOut,
    AdminReviewUpdate,
    FacilitatorCreate,
    InvitationCodeCreate,
    InvitationCodeUpdate,
    ModuleSubmissionDecision,
    PortalSettingUpdate,
)
from app.models.enums import CertificateType, PaymentLetterStatus
from app.services import storage
from app.services.documents.certificate import generate_completion_certificate_pdf
from app.services.documents.contract import generate_contract_pdf
from app.services.documents.dossier import build_applicant_dossier_pdf
from app.services.email import send_approval_credentials_email, send_phase1_approval_email
from app.services.notification import create_notification as notify
from app.services.points import award_points

router = APIRouter(prefix="/admin", tags=["instructors-admin"])


@router.get("/overview", response_model=AdminOverviewOut)
async def overview(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    pending_applications = (await db.execute(
        select(func.count()).select_from(ApplicationReview).where(ApplicationReview.status == ApplicationStatus.under_review)
    )).scalar_one()
    pending_payment_signatures = (await db.execute(
        select(func.count()).select_from(PaymentLetter).where(PaymentLetter.status == PaymentLetterStatus.published)
    )).scalar_one()
    total_instructors = (await db.execute(select(func.count()).select_from(User).where(User.roles.any("instructor")))).scalar_one()
    total_applicants = (await db.execute(select(func.count()).select_from(User).where(User.roles.any("applicant")))).scalar_one()
    total_facilitators = (await db.execute(select(func.count()).select_from(User).where(User.roles.any("facilitator")))).scalar_one()
    active_users_30d = (await db.execute(
        select(func.count()).select_from(User).where(User.last_login_at >= datetime.now(timezone.utc) - timedelta(days=30))
    )).scalar_one()

    university_rows = (await db.execute(
        select(ApplicantProfile.university, func.count())
        .join(User, User.id == ApplicantProfile.user_id)
        .where(ApplicantProfile.university.is_not(None))
        .group_by(ApplicantProfile.university)
        .order_by(func.count().desc())
    )).all()
    university_distribution = [{"name": name, "count": count} for name, count in university_rows]

    city_rows = (await db.execute(
        select(ApplicantProfile.city_of_residence, func.count())
        .join(User, User.id == ApplicantProfile.user_id)
        .where(ApplicantProfile.city_of_residence.is_not(None))
        .group_by(ApplicantProfile.city_of_residence)
        .order_by(func.count().desc())
    )).all()
    city_distribution = [{"name": name, "count": count} for name, count in city_rows]

    month_expr = func.to_char(User.created_at, "YYYY-MM")
    trend_rows = (await db.execute(
        select(month_expr, func.count())
        .where(User.roles.any("applicant"))
        .group_by(month_expr)
        .order_by(month_expr)
    )).all()
    signup_trend = [{"month": month, "count": count} for month, count in trend_rows]

    return AdminOverviewOut(
        pending_applications=pending_applications, pending_payment_signatures=pending_payment_signatures,
        total_instructors=total_instructors, total_applicants=total_applicants,
        total_facilitators=total_facilitators, active_users_30d=active_users_30d,
        university_distribution=university_distribution, city_distribution=city_distribution,
        signup_trend=signup_trend,
    )


@router.get("/applicants")
async def list_applicants(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    rows = (await db.execute(
        select(User, ApplicationReview, ApplicantProfile)
        .join(ApplicationReview, ApplicationReview.user_id == User.id)
        .outerjoin(ApplicantProfile, ApplicantProfile.user_id == User.id)
        .where(User.roles.any("applicant"))
        .order_by(User.created_at.desc())
    )).all()
    return [
        {
            "id": str(u.id), "full_name": u.full_name, "email": u.email,
            "status": review.status, "feedback": review.feedback,
            "university": profile.university if profile else None,
            "referred_by_ambassador_id": str(u.invited_by_id) if u.invited_by_id else None,
            "created_at": u.created_at,
        }
        for u, review, profile in rows
    ]


@router.get("/applicants/{user_id}")
async def applicant_detail(
    user_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    user = (await db.execute(select(User).where(User.id == user_id, User.roles.any("applicant")))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Applicant not found")
    profile = (await db.execute(select(ApplicantProfile).where(ApplicantProfile.user_id == user_id))).scalars().first()
    review = (await db.execute(select(ApplicationReview).where(ApplicationReview.user_id == user_id))).scalars().first()
    videos = (await db.execute(
        select(VideoSubmission).where(VideoSubmission.user_id == user_id).order_by(VideoSubmission.video_no)
    )).scalars().all()
    presentation = (await db.execute(
        select(PresentationSubmission).where(PresentationSubmission.user_id == user_id)
    )).scalars().first()
    assessment = (await db.execute(
        select(AssessmentSubmission).where(AssessmentSubmission.user_id == user_id)
    )).scalars().first()

    # Best-effort "invite code used at signup": instructor_apply never persists
    # the code the applicant typed against their own row (it's validated then
    # discarded) — only the referring ambassador's own sharable invite_code is
    # reconstructible, via users.invited_by_id. Admin-issued invitation_codes
    # (the other code family instructor_apply accepts) leave no per-applicant
    # trace at all, so this is genuinely best-effort, not the exact code typed.
    invite_code_used = None
    if user.invited_by_id:
        ambassador = (await db.execute(select(User).where(User.id == user.invited_by_id))).scalars().first()
        invite_code_used = ambassador.invite_code if ambassador else None

    # Expose checklist modules, items (grouped by section, matching the
    # reference admin_dashboard.html), progress, and submissions.
    from app.models.instructors.checklist import ChecklistModule, ChecklistItem, UserChecklistProgress
    from app.models.instructors.module_submission import ModuleSubmission

    modules = (await db.execute(select(ChecklistModule).order_by(ChecklistModule.sort_order))).scalars().all()
    module_ids = [m.id for m in modules]

    sections = (await db.execute(
        select(ModuleSection).where(ModuleSection.module_id.in_(module_ids)).order_by(ModuleSection.sort_order)
    )).scalars().all()
    sections_by_module: dict = {}
    for s in sections:
        sections_by_module.setdefault(s.module_id, []).append(s)

    items = (await db.execute(
        select(ChecklistItem).where(ChecklistItem.module_id.in_(module_ids)).order_by(ChecklistItem.sort_order)
    )).scalars().all()
    items_by_module = {}
    for it in items:
        items_by_module.setdefault(it.module_id, []).append(it)

    item_ids = [it.id for it in items]
    progress_rows = (await db.execute(
        select(UserChecklistProgress).where(
            UserChecklistProgress.user_id == user_id,
            UserChecklistProgress.checklist_item_id.in_(item_ids),
        )
    )).scalars().all()
    completed_ids = {p.checklist_item_id for p in progress_rows if p.is_completed}

    submissions = (await db.execute(
        select(ModuleSubmission).where(
            ModuleSubmission.user_id == user_id, ModuleSubmission.module_id.in_(module_ids)
        )
    )).scalars().all()
    submission_by_module = {s.module_id: s for s in submissions}

    def _item_out(it) -> dict:
        return {
            "id": str(it.id),
            "item_code": it.item_code,
            "title": it.title,
            "is_completed": it.id in completed_ids,
        }

    modules_data = []
    for m in modules:
        module_items = items_by_module.get(m.id, [])
        module_sections = sections_by_module.get(m.id, [])
        sub = submission_by_module.get(m.id)
        items_no_section = [it for it in module_items if it.section_id is None]
        modules_data.append({
            "id": str(m.id),
            "title": m.title,
            "sort_order": m.sort_order,
            # Flat list — kept for existing checked/total-count logic.
            "checklist_items": [_item_out(it) for it in module_items],
            # Section-grouped view, matching the reference admin_dashboard.html.
            "items_no_section": [_item_out(it) for it in items_no_section],
            "sections": [
                {
                    "id": str(sec.id),
                    "title": sec.title,
                    "items": [_item_out(it) for it in module_items if it.section_id == sec.id],
                }
                for sec in module_sections
            ],
            "submission": {
                "id": str(sub.id),
                "file_url": await storage.resolve_url(sub.bucket, sub.file_path, sub.file_url),
                "original_filename": sub.original_filename,
                "notes_text": sub.notes_text,
                "status": sub.status.value if sub.status else None,
                "feedback": sub.feedback,
            } if sub else None
        })

    return {
        "id": str(user.id), "full_name": user.full_name, "email": user.email, "phone": user.phone,
        "invite_code_used": invite_code_used,
        "profile": profile, "review": {"status": review.status, "feedback": review.feedback} if review else None,
        "videos": videos, "presentation_link": presentation.video_link if presentation else None,
        "assessment": {
            "file_url": await storage.resolve_url(assessment.bucket, assessment.file_path, assessment.file_url),
            "google_drive_link": assessment.google_drive_link,
            "comments": assessment.comments,
            "submitted_at": assessment.submitted_at,
        } if assessment else None,
        "modules": modules_data,
    }


@router.put("/applicants/{user_id}/review")
async def review_applicant(
    user_id: uuid.UUID,
    body: AdminReviewUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """The applicant pipeline state machine (instructors/HANDOFF.md §4).
    Admin may only move an application out of `under_review`."""
    user = (await db.execute(select(User).where(User.id == user_id, User.roles.any("applicant")))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Applicant not found")

    review = (await db.execute(select(ApplicationReview).where(ApplicationReview.user_id == user_id))).scalars().first()
    if not review:
        raise HTTPException(status_code=404, detail="Application review not found")
    if review.status in (ApplicationStatus.approved, ApplicationStatus.rejected):
        raise HTTPException(status_code=400, detail="Application is already finalized")

    review.status = body.status
    review.admin_id = current_user.id
    review.feedback = body.feedback
    review.reviewed_at = datetime.now(timezone.utc)

    email_sent = None

    if body.status == ApplicationStatus.phase_1_approved:
        email_sent = await send_phase1_approval_email(user.email, user.full_name)

    elif body.status == ApplicationStatus.approved:
        # Promote to instructor (replace 'applicant' — cleaner than keeping both, per PLAN §9.2)
        user.roles = [UserRole.instructor]

        profile = (await db.execute(select(ApplicantProfile).where(ApplicantProfile.user_id == user_id))).scalars().first()
        living_area = (profile.city_of_residence if profile and profile.city_of_residence else None) or \
            (profile.country if profile else "United Arab Emirates")

        contract_bytes = await asyncio.to_thread(generate_contract_pdf, user.full_name, living_area)
        contract_bucket, contract_path = "contracts", f"{user_id}/agreement.pdf"
        contract_url = await storage.upload_file(contract_bucket, contract_path, contract_bytes, "application/pdf")

        inst_profile = (await db.execute(
            select(InstructorProfile).where(InstructorProfile.user_id == user_id)
        )).scalars().first()
        if inst_profile:
            inst_profile.contract_url = contract_url
            inst_profile.contract_path = contract_path
        else:
            db.add(InstructorProfile(user_id=user_id, contract_url=contract_url, contract_path=contract_path))

        # Completion certificate auto-fires here — this approval is the one clean,
        # already-existing event for it (PLAN §8.2). Role-generic generator, same
        # one used for the interns-admin manual trigger (routers/interns/admin.py).
        cert_bytes = generate_completion_certificate_pdf(user.full_name, "Instructor Program")
        cert_bucket, cert_path = "certificates", f"{user_id}/instructor_completion.pdf"
        cert_url = await storage.upload_file(cert_bucket, cert_path, cert_bytes, "application/pdf")
        db.add(Certificate(
            user_id=user_id, type=CertificateType.instructor_completion, file_url=cert_url,
            bucket=cert_bucket, file_path=cert_path, generated_by=current_user.id,
        ))

        email_sent = await send_approval_credentials_email(
            user.email, user.full_name, contract_pdf=contract_bytes
        )

        if user.invited_by_id:
            await award_points(db, user.invited_by_id, 1000, f"Recruited instructor: {user.full_name}")
            await notify(db, user.invited_by_id, "Instructor Approved!",
                         f"{user.full_name}, whom you referred, was approved as an instructor — you earned points.", type="ambassador")

    # research_approved (Phase-2 gate) + rejected: no email, by design — the
    # applicant checks the portal for those (matches the source pipeline).

    await db.commit()
    return {"status": review.status, "email_sent": email_sent}


@router.put("/applicants/{user_id}/modules/{module_id}/review")
async def review_module_submission(
    user_id: uuid.UUID,
    module_id: uuid.UUID,
    body: ModuleSubmissionDecision,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Per-module PDF approve/reject + reviewer note (assessment page)."""
    sub = (await db.execute(
        select(ModuleSubmission).where(
            ModuleSubmission.user_id == user_id, ModuleSubmission.module_id == module_id
        )
    )).scalars().first()
    if not sub:
        raise HTTPException(status_code=404, detail="Module submission not found")
    sub.status = body.status
    sub.feedback = body.feedback
    sub.reviewed_at = datetime.now(timezone.utc)
    sub.reviewer_admin_id = current_user.id
    await db.commit()
    return {"module_id": str(module_id), "status": sub.status.value, "feedback": sub.feedback}


@router.delete("/applicants/{user_id}")
async def delete_applicant(
    user_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """Delete an applicant account and everything hanging off it (FK cascades
    cover reviews/videos/modules/submissions/checklist progress)."""
    user = (await db.execute(select(User).where(User.id == user_id, User.roles.any("applicant")))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Applicant not found")
    await db.delete(user)
    await db.commit()
    return {"status": "deleted"}


@router.get("/applicants/{user_id}/dossier")
async def export_applicant_dossier(
    user_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """Consolidated PDF: cover + one divider per module + each module's uploaded
    PDF merged in (the source's "Export Consolidated PDF")."""
    user = (await db.execute(select(User).where(User.id == user_id, User.roles.any("applicant")))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Applicant not found")
    review = (await db.execute(select(ApplicationReview).where(ApplicationReview.user_id == user_id))).scalars().first()

    mods = (await db.execute(select(ChecklistModule).order_by(ChecklistModule.sort_order))).scalars().all()
    subs = (await db.execute(
        select(ModuleSubmission).where(ModuleSubmission.user_id == user_id)
    )).scalars().all()
    sub_by_module = {s.module_id: s for s in subs}

    modules_payload = []
    async with httpx.AsyncClient(timeout=30) as client:
        for m in mods:
            sub = sub_by_module.get(m.id)
            pdf_bytes = None
            if sub and sub.file_url and (sub.original_filename or "").lower().endswith(".pdf"):
                try:
                    resp = await client.get(sub.file_url)
                    if resp.status_code == 200:
                        pdf_bytes = resp.content
                except Exception:  # noqa: BLE001 — unreachable/expired URL, divider still lists it
                    pdf_bytes = None
            modules_payload.append({
                "title": m.title,
                "status": sub.status.value if sub else None,
                "filename": sub.original_filename if sub else None,
                "pdf_bytes": pdf_bytes,
            })

    pdf = await asyncio.to_thread(
        build_applicant_dossier_pdf,
        user.full_name, user.email,
        review.status.value if review else "in_progress",
        modules_payload,
    )
    safe = "".join(c for c in user.full_name if c.isalnum() or c in " -_").strip().replace(" ", "_")
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="dossier_{safe or user_id}.pdf"'},
    )


# ── Invitation codes ───────────────────────────────────────────

@router.get("/invitations")
async def list_invitations(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    rows = (await db.execute(select(InvitationCode).order_by(InvitationCode.created_at.desc()))).scalars().all()
    return rows


@router.post("/invitations", status_code=201)
async def create_invitation(
    body: InvitationCodeCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    code = InvitationCode(code=body.code.strip().upper(), max_uses=body.max_uses, is_active=body.is_active)
    db.add(code)
    await db.commit()
    await db.refresh(code)
    return code


@router.put("/invitations/{invitation_id}")
async def update_invitation(
    invitation_id: uuid.UUID, body: InvitationCodeUpdate,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin),
):
    code = (await db.execute(select(InvitationCode).where(InvitationCode.id == invitation_id))).scalars().first()
    if not code:
        raise HTTPException(status_code=404, detail="Invitation code not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(code, field, value)
    await db.commit()
    await db.refresh(code)
    return code


@router.delete("/invitations/{invitation_id}")
async def delete_invitation(
    invitation_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    code = (await db.execute(select(InvitationCode).where(InvitationCode.id == invitation_id))).scalars().first()
    if not code:
        raise HTTPException(status_code=404, detail="Invitation code not found")
    await db.delete(code)
    await db.commit()
    return {"status": "deleted"}


# ── Facilitator accounts (admin-created only — no public signup) ─

@router.get("/facilitators")
async def list_facilitators(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    rows = (await db.execute(
        select(User).where(User.roles.any("facilitator")).order_by(User.created_at.desc())
    )).scalars().all()
    return [{"id": str(u.id), "full_name": u.full_name, "email": u.email, "created_at": u.created_at} for u in rows]


@router.post("/facilitators", status_code=201)
async def create_facilitator(
    body: FacilitatorCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    existing = (await db.execute(select(User.id).where(User.email == body.email))).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        full_name=body.full_name, email=body.email, password_hash=get_password_hash(body.password),
        roles=[UserRole.facilitator], status="active", must_change_password=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": str(user.id), "full_name": user.full_name, "email": user.email}


# ── Instructor directory ──────────────────────────────────────

@router.get("/instructors")
async def list_instructors(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    rows = (await db.execute(
        select(User, InstructorProfile)
        .outerjoin(InstructorProfile, InstructorProfile.user_id == User.id)
        .where(User.roles.any("instructor"))
        .order_by(User.created_at.desc())
    )).all()
    return [
        {
            "id": str(u.id), "full_name": u.full_name, "email": u.email, "status": u.status,
            "linkedin_url": u.linkedin_url, "created_at": u.created_at,
        }
        for u, p in rows
    ]


@router.get("/instructors/{user_id}")
async def instructor_detail(
    user_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    user = (await db.execute(select(User).where(User.id == user_id, User.roles.any("instructor")))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Instructor not found")
    profile = (await db.execute(select(InstructorProfile).where(InstructorProfile.user_id == user_id))).scalars().first()
    documents = (await db.execute(select(InstructorDocument).where(InstructorDocument.user_id == user_id))).scalars().all()
    return {
        "id": str(user.id), "full_name": user.full_name, "email": user.email, "status": user.status,
        "profile": profile, "documents": documents,
    }


# Settings moved to app.routers.admin.settings
