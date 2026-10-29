"""Generic user management (PLAN §9.4) — not domain-specific, since the `users`
table is shared across all 8 roles.
"""

import base64
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.application import Application
from app.models.certificate import Certificate
from app.models.document import Document
from app.models.enums import CertificateType, UserRole
from app.models.id_card import IdCard
from app.models.lms.author_profile import LmsAuthorProfile
from app.models.inventory.city import City
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.checklist import ChecklistModule
from app.models.instructors.instructor_document import InstructorDocument
from app.models.instructors.instructor_profile import InstructorProfile
from app.models.instructors.module_submission import ModuleSubmission
from app.models.instructors.payment import PaymentLetter
from app.models.instructors.presentation_submission import PresentationSubmission
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.user import User
from app.schemas.documents import DossierItem, UserDossierOut
from app.schemas.instructors.instructor import IdCardOut
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services.documents.card_id import format_card_id
from app.services import storage, user as user_service
from app.services.countries import COUNTRY_NAMES
from app.services.documents.id_card import ensure_card_id, render_card_back_png, render_card_png
from app.services.documents.user_zip import build_user_documents_zip

router = APIRouter(prefix="/users", tags=["admin"])

_CERT_LABEL = {
    CertificateType.workshop_delivery: "Workshop Delivery Certificate",
    CertificateType.internship_completion: "Internship Completion Certificate",
    CertificateType.instructor_completion: "Instructor Completion Certificate",
}


async def _attach_org_and_author(db: AsyncSession, user: User, row: UserOut) -> UserOut:
    row.card_id = format_card_id(user.card_number, user.roles) if user.card_number is not None else None
    if "lms_author" in user.role_values:
        ap = await db.get(LmsAuthorProfile, user.id)
        if ap:
            row.author_can_publish = ap.can_publish
            row.author_scope_all = ap.scope_all
    org = None
    if user.organization_id:
        org = await db.get(Organization, user.organization_id)
    if org is None:
        org = (
            await db.execute(select(Organization).where(Organization.owner_user_id == user.id))
        ).scalars().first()
    if org is None and user.contact_id:
        contact = await db.get(Contact, user.contact_id)
        if contact and contact.organization_id:
            org = await db.get(Organization, contact.organization_id)
    if org is not None:
        row.organization_id = org.id
        row.organization_name = org.name_latin
        row.organization_name_arabic = org.name_arabic
        row.organization_type = org.org_type
        row.organization_country = org.country
        row.organization_city = org.city
        row.org_is_approved = org.is_approved
        row.org_can_publish_events = org.can_publish_events
        row.org_can_author_courses = org.can_author_courses
        row.org_can_publish_courses = org.can_publish_courses
        row.org_course_scope_all = org.course_scope_all
        row.org_allowed_course_ids = [str(cid) for cid in (org.allowed_course_ids or [])]
        row.org_quiz_scope = org.quiz_scope
        row.org_allowed_quiz_template_ids = [str(tid) for tid in (org.allowed_quiz_template_ids or [])]
        row.org_max_events = org.max_events
        row.org_max_programs = org.max_programs
        row.org_max_cohorts = org.max_cohorts
        row.org_max_students_per_cohort = org.max_students_per_cohort
        row.org_max_observers_per_cohort = org.max_observers_per_cohort
    return row


@router.post("", response_model=UserOut)
async def create_user(user_in: UserCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    user = await user_service.create_user(db, user_in)
    row = UserOut.model_validate(user)
    return await _attach_org_and_author(db, user, row)


@router.get("", response_model=List[UserOut])
async def read_users(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    """Every account, with the school and grade behind each one.

    School and grade live on the linked spine `Contact`, not on `users`, so
    the students table used to have no way to show them — which is most of
    what makes a student row identifiable at a camp. Resolved here in two
    batched queries rather than per row.
    """
    users = await user_service.get_users(db)

    contact_ids = [u.contact_id for u in users if u.contact_id]
    contacts = {
        c.id: c for c in (
            (await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars().all()
            if contact_ids else []
        )
    }
    all_orgs = (await db.execute(select(Organization))).scalars().all()
    orgs = {o.id: o for o in all_orgs}
    orgs_by_owner = {o.owner_user_id: o for o in all_orgs if o.owner_user_id}

    author_profiles = {
        p.user_id: p for p in (
            (await db.execute(select(LmsAuthorProfile))).scalars().all()
        )
    }

    out: list[UserOut] = []
    for user in users:
        contact = contacts.get(user.contact_id) if user.contact_id else None
        org = (orgs.get(user.organization_id) if user.organization_id else None) or orgs_by_owner.get(user.id) or (orgs.get(contact.organization_id) if contact and contact.organization_id else None)
        ap = author_profiles.get(user.id)
        row = UserOut.model_validate(user)
        row.grade = contact.grade if contact else None
        row.school_name = org.name_latin if org else None
        row.card_id = format_card_id(user.card_number, user.roles) if user.card_number is not None else None
        row.author_can_publish = ap.can_publish if ap else None
        row.author_scope_all = ap.scope_all if ap else None
        if org is not None:
            row.organization_id = org.id
            row.organization_name = org.name_latin
            row.organization_name_arabic = org.name_arabic
            row.organization_type = org.org_type
            row.organization_country = org.country
            row.organization_city = org.city
            row.org_is_approved = org.is_approved
            row.org_can_publish_events = org.can_publish_events
            row.org_can_author_courses = org.can_author_courses
            row.org_can_publish_courses = org.can_publish_courses
            row.org_course_scope_all = org.course_scope_all
            row.org_allowed_course_ids = [str(cid) for cid in (org.allowed_course_ids or [])]
            row.org_quiz_scope = org.quiz_scope
            row.org_allowed_quiz_template_ids = [str(tid) for tid in (org.allowed_quiz_template_ids or [])]
            row.org_max_events = org.max_events
            row.org_max_programs = org.max_programs
            row.org_max_cohorts = org.max_cohorts
            row.org_max_students_per_cohort = org.max_students_per_cohort
            row.org_max_observers_per_cohort = org.max_observers_per_cohort
        out.append(row)
    return out


@router.patch("/{id}", response_model=UserOut)
async def update_user(id: UUID, user_in: UserUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    user = await user_service.update_user(db, id, user_in, actor_user_id=current_user.id)
    row = UserOut.model_validate(user)
    return await _attach_org_and_author(db, user, row)


@router.delete("/{id}")
async def delete_user(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    target = await user_service.get_user_by_id(db, id)
    if settings.is_test_email(target.email) and "admin" not in target.role_values:
        from app.services.test_account_cleanup import cascade_delete_test_account
        return await cascade_delete_test_account(db, user_id=id)
    return await user_service.delete_user(db, id)


@router.post("/{id}/reset-link")
async def generate_user_password_reset_link(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Generates a direct password-set/reset link for a user account (valid for 7 days)."""
    from datetime import timedelta
    from app.core.config import settings
    from app.core.security import create_password_set_token

    target = await db.get(User, id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    token = create_password_set_token(target.id, expires_delta=timedelta(days=7))
    base = (settings.FRONTEND_URL or "http://localhost:5173").rstrip("/")
    return {
        "user_id": str(target.id),
        "email": target.email,
        "reset_url": f"{base}/set-password?token={token}",
    }


@router.get("/{id}/documents", response_model=UserDossierOut)
async def get_user_dossier(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    """Everything on file for one person, across every domain — the admin
    "all documents for this user" dossier (PIVOT_HANDOFF §Phase 5)."""
    target = (await db.execute(select(User).where(User.id == id))).scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    items: list[DossierItem] = []

    for d in (await db.execute(select(Document).where(Document.user_id == id))).scalars().all():
        items.append(DossierItem(
            category="Documents", label=d.label, date=d.generated_at,
            url=await storage.resolve_url(d.bucket, d.file_path, d.file_url),
            id=d.id,
        ))

    for c in (await db.execute(select(Certificate).where(Certificate.user_id == id))).scalars().all():
        items.append(DossierItem(
            category="Certificates",
            label=_CERT_LABEL.get(c.type, str(c.type)),
            date=c.generated_at,
            url=await storage.resolve_url(c.bucket, c.file_path, c.file_url),
            meta=c.workshop_name,
            id=c.id,
        ))

    for v in (await db.execute(select(InstructorDocument).where(InstructorDocument.user_id == id))).scalars().all():
        items.append(DossierItem(
            category="Personal Vault", label=v.document_type, date=v.uploaded_at,
            url=await storage.resolve_url(v.bucket, v.file_path, v.file_url),
        ))

    subs = (await db.execute(
        select(ModuleSubmission, ChecklistModule.title)
        .join(ChecklistModule, ChecklistModule.id == ModuleSubmission.module_id)
        .where(ModuleSubmission.user_id == id)
    )).all()
    for sub, module_title in subs:
        items.append(DossierItem(
            category="Module Submissions",
            label=f"{module_title} — {sub.original_filename or 'submission'}",
            date=sub.submitted_at,
            url=await storage.resolve_url(sub.bucket, sub.file_path, sub.file_url),
            meta=sub.status.value if hasattr(sub.status, "value") else str(sub.status),
        ))

    pres = (await db.execute(select(PresentationSubmission).where(PresentationSubmission.user_id == id))).scalars().first()
    if pres:
        items.append(DossierItem(
            category="Applicant Pipeline", label="Presentation Submission", date=pres.submitted_at, url=pres.video_link,
        ))

    applicant_profile = (await db.execute(select(ApplicantProfile).where(ApplicantProfile.user_id == id))).scalars().first()
    if applicant_profile:
        residence_city = (
            await db.get(City, applicant_profile.city_of_residence_id)
        ) if applicant_profile.city_of_residence_id else None
        items.append(DossierItem(
            category="Applicant Pipeline",
            label="Applicant Profile",
            meta=f"{residence_city.name if residence_city else ''} "
                 f"{COUNTRY_NAMES.get(applicant_profile.country, applicant_profile.country or '')}".strip() or None,
        ))

    app_row = (await db.execute(
        select(Application).where(func.lower(Application.email) == (target.email or "").strip().lower()).order_by(Application.created_at.desc())
    )).scalars().first()
    if app_row and (app_row.cv_url or app_row.cv_path):
        items.append(DossierItem(
            category="Applicant Pipeline", label="CV / Resume", date=app_row.created_at,
            url=await storage.resolve_url("cvs", app_row.cv_path, app_row.cv_url),
        ))

    profile = (await db.execute(select(InstructorProfile).where(InstructorProfile.user_id == id))).scalars().first()
    if profile:
        if profile.contract_url or profile.contract_path:
            items.append(DossierItem(
                category="Contract", label="Contract", date=profile.created_at,
                url=await storage.resolve_url("contracts", profile.contract_path, profile.contract_url),
            ))
        if profile.signed_contract_url or profile.signed_contract_path:
            items.append(DossierItem(
                category="Contract", label="Signed Contract", date=profile.updated_at,
                url=await storage.resolve_url("contracts", profile.signed_contract_path, profile.signed_contract_url),
            ))

    for letter in (await db.execute(select(PaymentLetter).where(PaymentLetter.instructor_user_id == id))).scalars().all():
        if letter.pdf_url or letter.pdf_path:
            items.append(DossierItem(
                category="Payment Letters", label=f"Payment Letter ({letter.reference})",
                date=letter.created_at,
                url=await storage.resolve_url("payment-letters", letter.pdf_path, letter.pdf_url),
                meta=letter.status.value,
            ))
        if letter.signed_pdf_url or letter.signed_pdf_path:
            items.append(DossierItem(
                category="Payment Letters", label=f"Signed Payment Letter ({letter.reference})",
                date=letter.signed_at,
                url=await storage.resolve_url("payment-letters", letter.signed_pdf_path, letter.signed_pdf_url),
                meta=letter.status.value,
            ))

    for card in (await db.execute(select(IdCard).where(IdCard.user_id == id))).scalars().all():
        role_label = card.role.value if hasattr(card.role, "value") else str(card.role)
        items.append(DossierItem(
            category="ID Cards",
            label=f"ID Card — {role_label.title()}",
            date=card.generated_at,
            url=f"/admin/users/{id}/id-card?role={role_label}",
            meta=card.card_id,
        ))

    return UserDossierOut(items=items)


@router.get("/{id}/documents/zip")
async def download_user_documents_zip(
    id: UUID,
    include_generated: bool = Query(False, description="Include system-generated documents/certificates in addition to uploaded documents"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Download all uploaded documents for a user bundled into a ZIP archive."""
    zip_bytes, zip_filename = await build_user_documents_zip(
        user_id=id, db=db, include_generated=include_generated
    )
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )


@router.get("/{id}/id-card", response_model=IdCardOut)
async def get_user_id_card(
    id: UUID, role: UserRole, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin),
):
    """Admin view of another user's ID card — same renderer `id-card`/`me` uses,
    just gated on `require_admin` instead of self, for the dossier's ID Cards section."""
    target = (await db.execute(select(User).where(User.id == id))).scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if role not in target.roles:
        raise HTTPException(status_code=400, detail="User does not have this role")

    card_row = await ensure_card_id(db, target.id, role)
    await db.commit()

    photo_url = target.photo_url
    linkedin_url = target.linkedin_url

    photo_bytes = None
    if photo_url:
        from app.routers.instructors.instructor import _fetch_photo, _resolve_photo_url
        resolved = await _resolve_photo_url(photo_url)
        if resolved != photo_url:
            target.photo_url = resolved
            await db.commit()
            photo_url = resolved
        try:
            photo_bytes = await _fetch_photo(photo_url)
        except Exception:
            pass

    front_png = render_card_png(role, photo_bytes, linkedin_url, target.full_name)
    issue_date = card_row.generated_at or datetime.now(timezone.utc)
    back_png = render_card_back_png(role, card_row.card_id, issue_date)

    return IdCardOut(
        card_id=card_row.card_id,
        front_b64=base64.b64encode(front_png).decode(),
        back_b64=base64.b64encode(back_png).decode(),
        generated_at=card_row.generated_at,
        has_photo=bool(photo_url),
        has_linkedin=bool(linkedin_url),
        photo_url=photo_url,
        linkedin_url=linkedin_url,
    )
