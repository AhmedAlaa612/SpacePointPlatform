import asyncio
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

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
from app.models.document_template import DocumentTemplate
from app.models.inventory.city import City
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
from app.services.documents.id_card import ensure_card_number
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
from app.routers.instructors.instructor import _resolve_living_area
from app.services import storage
from app.services.documents.certificate import generate_completion_certificate_pdf
from app.services.documents.contract import format_contract_date, generate_contract_pdf
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
        select(City.name, func.count())
        .select_from(ApplicantProfile)
        .join(User, User.id == ApplicantProfile.user_id)
        .join(City, City.id == ApplicantProfile.city_of_residence_id)
        .group_by(City.name)
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

    city_ids = {p.city_of_residence_id for _, _, p in rows if p and p.city_of_residence_id}
    cities_by_id = {}
    if city_ids:
        cities_by_id = {c.id: c.name for c in (await db.execute(select(City).where(City.id.in_(city_ids)))).scalars().all()}

    return [
        {
            "id": str(u.id), "full_name": u.full_name, "email": u.email,
            "status": review.status, "feedback": review.feedback,
            "university": profile.university if profile else None,
            "city_of_residence": cities_by_id.get(profile.city_of_residence_id) if profile else None,
            "referred_by_ambassador_id": str(u.invited_by_id) if u.invited_by_id else None,
            "created_at": u.created_at,
            "submitted_at": review.submitted_at,
            "also_grant_role": profile.also_grant_role if profile else None,
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

    # The exact code typed at signup — sql/0017's users.invitation_code_used,
    # populated going forward by instructor_apply. Rows that predate that fix
    # (migrated from the legacy portal before the ETL carried this column
    # over, or created in the gap before this fix shipped) fall back to a
    # best-effort reconstruction: if they were referred by an ambassador, that
    # ambassador's own sharable invite_code — not the literal code typed, but
    # the closest recoverable equivalent.
    invite_code_used = user.invitation_code_used
    if not invite_code_used and user.invited_by_id:
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

    # Raw `profile` used to serialize fine when `city_of_residence` was a
    # plain string; it's now `city_of_residence_id` (a FK, not a name) —
    # resolve it here under the same "city_of_residence" key the frontend
    # already reads, same pattern `_location_out` uses for `Location.city_id`
    # (resolve the FK to a name; `country` stays a raw ISO code either way —
    # that's the frontend's job to display, same as everywhere else).
    profile_out = None
    if profile:
        residence_city = (
            await db.get(City, profile.city_of_residence_id)
        ) if profile.city_of_residence_id else None
        profile_out = {c.name: getattr(profile, c.name) for c in ApplicantProfile.__table__.columns}
        profile_out["city_of_residence"] = residence_city.name if residence_city else None

    return {
        "id": str(user.id), "full_name": user.full_name, "email": user.email, "phone": user.phone,
        "invite_code_used": invite_code_used,
        "cv_url": await storage.get_signed_url("cvs", profile.cv_path) if profile and profile.cv_path else None,
        "profile": profile_out, "review": {"status": review.status, "feedback": review.feedback} if review else None,
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
        profile = (await db.execute(select(ApplicantProfile).where(ApplicantProfile.user_id == user_id))).scalars().first()

        # Promote to instructor: swap 'applicant' for 'instructor' and leave every
        # other role the person already holds untouched.
        #
        # This used to assign a fresh set (`user.roles = [UserRole.instructor]`),
        # which silently destroyed anything else they had — an ambassador who
        # completed instructor onboarding stopped being an ambassador. It also made
        # holding two roles impossible in general, which is why `also_grant_role`
        # exists at all: a single extra role smuggled through the wipe.
        #
        # The underlying confusion is that 'applicant' isn't a capability like the
        # others, it's pipeline state (already tracked on application_reviews.status).
        # Dropping just that one and adding to the rest is what "promotion" actually
        # means. also_grant_role still applies — it carries a role the person was
        # approved for elsewhere but never held yet (an intern application routed
        # into this pipeline; see routers/admin/applications.py::onboard_application).
        kept = {r for r in user.role_values if r != UserRole.applicant.value}
        kept.add(UserRole.instructor.value)
        if profile and profile.also_grant_role:
            try:
                kept.add(UserRole(profile.also_grant_role).value)
            except ValueError:
                pass
        user.roles = sorted(kept)

        # Shared with the lazy/signing paths (routers/instructors/instructor.py)
        # so a missing city is handled the same way everywhere: this must never
        # resolve to a country name, since the contract template's own static
        # text already appends ", United Arab Emirates" right after it.
        living_area = await _resolve_living_area(db, user)

        # Frozen the moment approval grants the role — this, not date.today(),
        # is what the contract's date prints from from here on (bug fix,
        # 2026-08-17; see instructor.py::_ensure_contract).
        instructor_since = datetime.now(timezone.utc).date()
        contract_date = format_contract_date(instructor_since)
        contract_bytes = await asyncio.to_thread(
            generate_contract_pdf, user.full_name, living_area, contract_date=contract_date
        )
        contract_bucket, contract_path = "contracts", f"{user_id}/agreement.pdf"
        contract_url = await storage.upload_file(contract_bucket, contract_path, contract_bytes, "application/pdf")

        inst_profile = (await db.execute(
            select(InstructorProfile).where(InstructorProfile.user_id == user_id)
        )).scalars().first()
        if inst_profile:
            inst_profile.contract_url = contract_url
            inst_profile.contract_path = contract_path
            if inst_profile.instructor_since is None:
                inst_profile.instructor_since = instructor_since
        else:
            db.add(InstructorProfile(
                user_id=user_id, contract_url=contract_url, contract_path=contract_path,
                instructor_since=instructor_since,
            ))

        # Completion certificate auto-fires here — this approval is the one clean,
        # already-existing event for it (PLAN §8.2). Role-generic generator, same
        # one used for the interns-admin manual trigger (routers/interns/admin.py).
        # Rendered from the editable `instructor_completion` system template
        # (seeded by migration a3f7c91d0037) so admins can change the wording
        # without a code change — same pattern as `workshop_delivery` in
        # payments.py. Falls back to the original hardcoded wording if the
        # template row is somehow missing (e.g. migration not yet applied).
        cert_template = (await db.execute(
            select(DocumentTemplate).where(DocumentTemplate.key == "instructor_completion")
        )).scalars().first()
        cert_body = (cert_template.body_text if cert_template else "Instructor Program") \
            .replace("{name}", escape(user.full_name))
        cert_bytes = generate_completion_certificate_pdf(user.full_name, cert_body)
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
    # kind='instructor' only (2026-08-13) — student batch codes are ops-
    # managed at /lms/admin/invite-codes and must not appear here, where
    # editing one would silently change a school's signup code.
    rows = (await db.execute(
        select(InvitationCode).where(InvitationCode.kind == "instructor")
        .order_by(InvitationCode.created_at.desc())
    )).scalars().all()
    return rows


@router.post("/invitations", status_code=201)
async def create_invitation(
    body: InvitationCodeCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    code = InvitationCode(
        code=body.code.strip().upper(), max_uses=body.max_uses, is_active=body.is_active, kind="instructor",
    )
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
    await db.flush()
    await ensure_card_number(db, user)
    await db.commit()
    await db.refresh(user)
    return {"id": str(user.id), "full_name": user.full_name, "email": user.email}


# ── Instructor directory ──────────────────────────────────────

@router.get("/instructors")
async def list_instructors(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    """Instructor directory, with the city fields the admin list filters on.

    Cities are returned as both id and name (2026-08-09): the id is what the
    filter matches on (exact, same as staffing city-matching — never compare
    names), the name is what the row renders.

    Residence resolves `users.city_id` -> `users.city_other` ->
    `ApplicantProfile.city_of_residence_id`, the same precedence as
    `_resolve_living_area` in routers/instructors/instructor.py. Reading only
    `users.city_id` is wrong in practice: instructors who came through the
    applicant pipeline before that general field existed (2026-08-08) have
    their city ONLY on the applicant profile, and would show as "No city"
    here while their contract correctly prints it.

    Open-to-work cities come from `ApplicantProfile.deliver_city_ids`, so
    instructors with no applicant profile simply have none.
    """
    rows = (await db.execute(
        select(User, ApplicantProfile)
        .outerjoin(ApplicantProfile, ApplicantProfile.user_id == User.id)
        .where(User.roles.any("instructor"))
        .order_by(User.created_at.desc())
    )).all()

    # One lookup for every city referenced by any row, rather than per-user.
    needed: set[uuid.UUID] = set()
    for u, p in rows:
        if u.city_id:
            needed.add(u.city_id)
        if p and p.city_of_residence_id:
            needed.add(p.city_of_residence_id)
        needed.update(p.deliver_city_ids or [] if p else [])
    city_names: dict[uuid.UUID, str] = {}
    if needed:
        found = (await db.execute(select(City).where(City.id.in_(needed)))).scalars().all()
        city_names = {c.id: c.name for c in found}

    out = []
    for u, p in rows:
        deliver_ids = list(p.deliver_city_ids or []) if p else []
        # Structured id first, applicant-profile id second; city_other is a
        # display-only fallback with no id, so it can be shown but not
        # filtered on (the filter's options are built from ids).
        city_id = u.city_id or (p.city_of_residence_id if p else None)
        out.append({
            "id": str(u.id), "full_name": u.full_name, "email": u.email, "status": u.status,
            "linkedin_url": u.linkedin_url, "created_at": u.created_at,
            "city_id": str(city_id) if city_id else None,
            "city_name": city_names.get(city_id) if city_id else u.city_other,
            "deliver_city_ids": [str(i) for i in deliver_ids if i in city_names],
            "deliver_city_names": [city_names[i] for i in deliver_ids if i in city_names],
        })
    return out


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
