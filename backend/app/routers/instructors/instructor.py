import asyncio
import base64
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import get_current_active_user, require_instructor, require_instructor_or_facilitator
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.id_card import IdCard
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.instructor_document import InstructorDocument
from app.models.instructors.instructor_profile import InstructorProfile
from app.models.instructors.payment import InstructorBankDetails
from app.models.user import User
from app.schemas.instructors.instructor import (
    BankDetailsOut,
    BankDetailsUpdate,
    IdCardOut,
    InstructorDocumentOut,
    InstructorProfileOut,
    InstructorProfileUpdate,
    SignContractRequest,
)
from app.services import storage
from app.services.documents.contract import generate_contract_pdf
from app.services.documents.id_card import ensure_card_id, render_card_png, render_card_back_png
from app.services.email import send_contract_signed_notification_email, send_signed_contract_email
from app.services.notification import create_notification as notify

router = APIRouter(tags=["instructors-instructor"])


async def _get_or_create_profile(db: AsyncSession, user_id: uuid.UUID) -> InstructorProfile:
    profile = (await db.execute(select(InstructorProfile).where(InstructorProfile.user_id == user_id))).scalars().first()
    if not profile:
        profile = InstructorProfile(user_id=user_id)
        db.add(profile)
        await db.flush()
    return profile


async def _profile_out(profile: InstructorProfile, user: User) -> InstructorProfileOut:
    """Contract URLs are generated at query time from the stored paths (A2);
    the legacy *_url columns are only a fallback for pre-migration rows."""
    return InstructorProfileOut(
        user_id=profile.user_id,
        linkedin_url=user.linkedin_url,
        photo_url=user.photo_url,
        contract_url=await storage.resolve_url("contracts", profile.contract_path, profile.contract_url),
        signed_contract_url=await storage.resolve_url("contracts", profile.signed_contract_path, profile.signed_contract_url),
        contract_signed_at=profile.contract_signed_at,
    )


@router.get("/profile", response_model=InstructorProfileOut)
async def get_profile(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor_or_facilitator)):
    profile = await _get_or_create_profile(db, current_user.id)
    return await _profile_out(profile, current_user)


@router.put("/profile", response_model=InstructorProfileOut)
async def update_profile(
    body: InstructorProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor_or_facilitator),
):
    profile = await _get_or_create_profile(db, current_user.id)
    if body.linkedin_url is not None:
        current_user.linkedin_url = body.linkedin_url
    await db.commit()
    return await _profile_out(profile, current_user)


@router.post("/contract/sign", response_model=InstructorProfileOut)
async def sign_contract(
    body: SignContractRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor),
):
    profile = (await db.execute(
        select(InstructorProfile).where(InstructorProfile.user_id == current_user.id)
    )).scalars().first()
    if not profile or not (profile.contract_path or profile.contract_url):
        raise HTTPException(status_code=404, detail="No contract on file to sign")
    if profile.contract_signed_at:
        raise HTTPException(status_code=400, detail="Contract already signed")

    applicant_profile = (await db.execute(
        select(ApplicantProfile).where(ApplicantProfile.user_id == current_user.id)
    )).scalars().first()
    living_area = (applicant_profile.city_of_residence if applicant_profile and applicant_profile.city_of_residence else None) or \
        (applicant_profile.country if applicant_profile else "United Arab Emirates")

    now = datetime.now(timezone.utc)
    try:
        pdf_bytes = await asyncio.to_thread(
            generate_contract_pdf,
            current_user.full_name,
            living_area,
            signed_date=now.strftime("%d %B %Y"),
            instructor_signature_b64=body.signature,
        )
        signed_path = f"{current_user.id}/signed.pdf"
        signed_url = await storage.upload_file("contracts", signed_path, pdf_bytes, "application/pdf")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Signed contract generation or upload failed: {str(e)}")

    profile.signed_contract_url = signed_url
    profile.signed_contract_path = signed_path
    profile.contract_signature_data = body.signature
    profile.contract_signed_at = now

    admins = (await db.execute(select(User).where(User.roles.any("admin")))).scalars().all()
    for admin in admins:
        await notify(db, admin.id, "Instructor Contract Signed",
                     f"{current_user.full_name} signed their instructor contract.", type="instructor")
        await send_contract_signed_notification_email(admin.email, current_user.full_name)
    await send_signed_contract_email(current_user.email, current_user.full_name, pdf_bytes)

    await db.commit()
    return await _profile_out(profile, current_user)


@router.get("/id-card", response_model=IdCardOut | None)
async def get_id_card(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor),
):
    """Render the ID card front and back on-the-fly."""
    card_row = await ensure_card_id(db, current_user.id, UserRole.instructor)

    photo_bytes = await _photo_bytes_for(current_user)
    await db.commit()

    front_png = render_card_png(UserRole.instructor, photo_bytes, current_user.linkedin_url, current_user.full_name)
    issue_date = card_row.generated_at or datetime.now(timezone.utc)
    back_png = render_card_back_png(UserRole.instructor, card_row.card_id, issue_date)

    return IdCardOut(
        card_id=card_row.card_id,
        front_b64=base64.b64encode(front_png).decode(),
        back_b64=base64.b64encode(back_png).decode(),
        generated_at=card_row.generated_at,
        has_photo=bool(current_user.photo_url or current_user.photo_path),
        has_linkedin=bool(current_user.linkedin_url),
    )


@router.post("/id-card", response_model=IdCardOut)
async def update_id_card(
    photo: UploadFile | None = None,
    linkedin_url: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor),
):
    """Upload/update profile photo and/or LinkedIn URL, then return rendered card front and back."""
    if linkedin_url is not None:
        current_user.linkedin_url = linkedin_url or None

    photo_bytes: bytes | None = None
    if photo and photo.filename:
        photo_bytes = await photo.read()
        photo_path = f"{current_user.id}{_ext(photo.filename)}"
        uploaded_url = await storage.upload_file(
            "profile_pictures",
            photo_path,
            photo_bytes,
            photo.content_type or "image/jpeg",
        )
        current_user.photo_url = uploaded_url
        current_user.photo_path = photo_path

    card_row = await ensure_card_id(db, current_user.id, UserRole.instructor)
    await db.commit()

    if photo_bytes is None:
        photo_bytes = await _photo_bytes_for(current_user)
        await db.commit()

    front_png = render_card_png(UserRole.instructor, photo_bytes, current_user.linkedin_url, current_user.full_name)
    issue_date = card_row.generated_at or datetime.now(timezone.utc)
    back_png = render_card_back_png(UserRole.instructor, card_row.card_id, issue_date)

    return IdCardOut(
        card_id=card_row.card_id,
        front_b64=base64.b64encode(front_png).decode(),
        back_b64=base64.b64encode(back_png).decode(),
        generated_at=card_row.generated_at,
        has_photo=bool(current_user.photo_url or current_user.photo_path),
        has_linkedin=bool(current_user.linkedin_url),
    )


@router.get("/id-card/pdf")
async def download_id_card_pdf(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor),
):
    """Stream the rendered card (front and back) as a downloadable PDF."""
    from io import BytesIO
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader
    from PIL import Image as PILImage

    card_row = await ensure_card_id(db, current_user.id, UserRole.instructor)
    photo_bytes = await _photo_bytes_for(current_user)
    await db.commit()

    front_png = render_card_png(UserRole.instructor, photo_bytes, current_user.linkedin_url, current_user.full_name)
    issue_date = card_row.generated_at or datetime.now(timezone.utc)
    back_png = render_card_back_png(UserRole.instructor, card_row.card_id, issue_date)

    # Wrap front and back in a CR80-sized PDF (3.375 × 2.125 in landscape)
    buf = BytesIO()
    w, h = 3.375 * inch, 2.125 * inch
    c = rl_canvas.Canvas(buf, pagesize=(w, h))
    
    # Page 1: Front
    front_img = PILImage.open(BytesIO(front_png)).rotate(-90, expand=True)
    img_buf1 = BytesIO()
    front_img.save(img_buf1, format="PNG")
    img_buf1.seek(0)
    c.drawImage(ImageReader(img_buf1), 0, 0, width=w, height=h)
    c.showPage()
    
    # Page 2: Back
    back_img = PILImage.open(BytesIO(back_png)).rotate(-90, expand=True)
    img_buf2 = BytesIO()
    back_img.save(img_buf2, format="PNG")
    img_buf2.seek(0)
    c.drawImage(ImageReader(img_buf2), 0, 0, width=w, height=h)
    c.showPage()

    c.save()

    filename = f"SpacePoint_ID_{card_row.card_id or current_user.id}.pdf"
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _fetch_photo(url: str) -> bytes:
    """Download photo bytes from a URL (Supabase public URL)."""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.content


_RENAMED_BUCKETS = {"instructor-photos", "intern-photos", "ambassador-photos"}
_PHOTO_BUCKET = "profile_pictures"


async def _resolve_photo_url(url: str | None) -> str | None:
    """Re-issue a signed URL if the stored URL still references a renamed bucket."""
    if not url:
        return url
    import re
    for old in _RENAMED_BUCKETS:
        m = re.search(rf"/object/sign/{re.escape(old)}/([^?]+)", url)
        if m:
            try:
                return await storage.get_signed_url(_PHOTO_BUCKET, m.group(1))
            except Exception:
                return url
    return url


async def _photo_bytes_for(user: User) -> bytes | None:
    """Profile-photo bytes for card rendering — prefers the durable photo_path
    (A2) via the storage backend; falls back to fetching the stored legacy URL.
    May refresh user.photo_url in place when a renamed-bucket URL gets
    re-signed — callers commit afterwards."""
    if getattr(user, "photo_path", None):
        try:
            return await storage.download_file(_PHOTO_BUCKET, user.photo_path)
        except Exception:
            pass
    if not user.photo_url:
        return None
    resolved = await _resolve_photo_url(user.photo_url)
    if resolved and resolved != user.photo_url:
        user.photo_url = resolved
    if not resolved:
        return None
    try:
        return await _fetch_photo(resolved)
    except Exception:
        return None


def _ext(filename: str | None) -> str:
    if not filename or "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1]


@router.get("/bank-details", response_model=BankDetailsOut)
async def get_bank_details(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)):
    bank = (await db.execute(
        select(InstructorBankDetails).where(InstructorBankDetails.user_id == current_user.id)
    )).scalars().first()
    return bank or BankDetailsOut()


@router.put("/bank-details", response_model=BankDetailsOut)
async def update_bank_details(
    body: BankDetailsUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)
):
    bank = (await db.execute(
        select(InstructorBankDetails).where(InstructorBankDetails.user_id == current_user.id)
    )).scalars().first()
    if not bank:
        bank = InstructorBankDetails(user_id=current_user.id)
        db.add(bank)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(bank, field, value)
    await db.commit()
    await db.refresh(bank)
    return bank


# ── Personal document vault (any authenticated role — table/paths are user-scoped, not instructor-specific) ──

async def _vault_doc_out(doc: InstructorDocument) -> InstructorDocumentOut:
    return InstructorDocumentOut(
        id=doc.id,
        document_type=doc.document_type,
        file_url=await storage.resolve_url(doc.bucket, doc.file_path, doc.file_url),
        uploaded_at=doc.uploaded_at,
    )


@router.get("/documents", response_model=list[InstructorDocumentOut])
async def list_documents(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)):
    rows = (await db.execute(
        select(InstructorDocument).where(InstructorDocument.user_id == current_user.id).order_by(InstructorDocument.uploaded_at.desc())
    )).scalars().all()
    return [await _vault_doc_out(d) for d in rows]


@router.post("/documents", response_model=InstructorDocumentOut, status_code=201)
async def upload_document(
    document_type: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    data = await file.read()
    path = f"{current_user.id}_{document_type}_{int(datetime.now(timezone.utc).timestamp())}{_ext(file.filename)}"
    file_url = await storage.upload_file("instructor-documents", path, data, file.content_type or "application/octet-stream")
    doc = InstructorDocument(
        user_id=current_user.id, document_type=document_type, file_url=file_url,
        bucket="instructor-documents", file_path=path,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return await _vault_doc_out(doc)


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)
):
    doc = (await db.execute(
        select(InstructorDocument).where(InstructorDocument.id == doc_id, InstructorDocument.user_id == current_user.id)
    )).scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)
    await db.commit()
    return {"status": "deleted"}
