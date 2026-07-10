"""Generic user management (PLAN §9.4) — not domain-specific, since the `users`
table is shared across all 8 roles.
"""

import base64
from datetime import datetime, timezone
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.application import Application
from app.models.certificate import Certificate
from app.models.document import Document
from app.models.enums import CertificateType, UserRole
from app.models.id_card import IdCard
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.checklist import ChecklistModule
from app.models.instructors.instructor_document import InstructorDocument
from app.models.instructors.instructor_profile import InstructorProfile
from app.models.instructors.module_submission import ModuleSubmission
from app.models.instructors.payment import PaymentLetter
from app.models.instructors.presentation_submission import PresentationSubmission
from app.models.user import User
from app.schemas.documents import DossierItem, UserDossierOut
from app.schemas.instructors.instructor import IdCardOut
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services import storage, user as user_service
from app.services.documents.id_card import ensure_card_id, render_card_back_png, render_card_png

router = APIRouter(prefix="/users", tags=["admin"])

_CERT_LABEL = {
    CertificateType.workshop_delivery: "Workshop Delivery Certificate",
    CertificateType.internship_completion: "Internship Completion Certificate",
    CertificateType.instructor_completion: "Instructor Completion Certificate",
}


@router.post("", response_model=UserOut)
async def create_user(user_in: UserCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await user_service.create_user(db, user_in)


@router.get("", response_model=List[UserOut])
async def read_users(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await user_service.get_users(db)


@router.patch("/{id}", response_model=UserOut)
async def update_user(id: UUID, user_in: UserUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await user_service.update_user(db, id, user_in)


@router.delete("/{id}")
async def delete_user(id: UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    return await user_service.delete_user(db, id)


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
        items.append(DossierItem(
            category="Applicant Pipeline",
            label="Applicant Profile",
            meta=f"{applicant_profile.city_of_residence or ''} {applicant_profile.country or ''}".strip() or None,
        ))

    app_row = (await db.execute(
        select(Application).where(Application.email == target.email).order_by(Application.created_at.desc())
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
