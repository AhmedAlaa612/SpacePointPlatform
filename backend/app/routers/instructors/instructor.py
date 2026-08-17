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
from app.models.inventory.city import City
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
from app.services.documents.contract import format_contract_date, generate_contract_pdf
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


async def _resolve_living_area(db: AsyncSession, user: User) -> str:
    """The CITY the contract prints as the Facilitator's residence — never a
    country. The template's own static text already appends ", United Arab
    Emirates" right after this value (agreement.docx paragraph 3), so if this
    ever resolves to a country name instead of a city, the printed contract
    reads "United Arab Emirates, United Arab Emirates" (or "Egypt, United
    Arab Emirates" — equally wrong, just less obviously broken). Checks
    `User.city_id`/`city_other` first — the general, structured field
    (2026-08-08) set regardless of how the account was created — then falls
    back to `ApplicantProfile.city_of_residence_id` for instructors who went
    through the applicant pipeline before that existed. Returns "" (not a
    country) when no city is on file anywhere; the template renders that
    gracefully as "residing in United Arab Emirates" with no dangling city."""
    if user.city_id:
        city = await db.get(City, user.city_id)
        if city:
            return city.name
    if user.city_other:
        return user.city_other

    applicant_profile = (await db.execute(
        select(ApplicantProfile).where(ApplicantProfile.user_id == user.id)
    )).scalars().first()
    if applicant_profile and applicant_profile.city_of_residence_id:
        residence_city = await db.get(City, applicant_profile.city_of_residence_id)
        if residence_city:
            return residence_city.name

    return ""


async def _ensure_contract(db: AsyncSession, profile: InstructorProfile, user: User) -> None:
    """Keep the unsigned contract in sync with current profile data.

    Two things this closes:

    1. Only the applicant-approval pipeline (routers/instructors/admin.py)
       used to generate the initial contract, so an instructor whose account
       was created any other way (seeded, invited directly, promoted
       pre-pipeline) never got a contract_url and the Personal Documents page
       had nothing to show.
    2. Even for instructors who did get one, it was generated once and then
       frozen — editing your name or city afterwards left the contract
       showing stale data, right up until you actually signed it (operator
       ask, 2026-08-09: pre-signing, this should behave like a live preview).

    So every unsigned-contract profile load re-renders from current
    name/city and overwrites the same storage path (not a new one —
    nothing else should be pointing at contract_path mid-flight, and this
    avoids piling up orphaned draft PDFs). The DATE printed is
    `instructor_since` — frozen at whatever event actually granted the
    instructor role — not `date.today()` (bug fix, 2026-08-17: the date
    used to silently drift forward every day the profile page was opened,
    which read as "it updates till it's signed"; the real intent is the
    date they became an instructor). Falls back to today only for the
    edge case of a pre-migration row that somehow has no instructor_since.
    Skips entirely once `contract_signed_at` is set — the signed PDF is the
    final, immutable record and this function must never touch it."""
    if profile.contract_signed_at or "instructor" not in user.role_values:
        return
    living_area = await _resolve_living_area(db, user)
    contract_date = format_contract_date(profile.instructor_since or datetime.now(timezone.utc).date())
    pdf_bytes = await asyncio.to_thread(generate_contract_pdf, user.full_name, living_area, contract_date=contract_date)
    contract_path = profile.contract_path or f"{user.id}/agreement.pdf"
    contract_url = await storage.upload_file("contracts", contract_path, pdf_bytes, "application/pdf")
    profile.contract_url = contract_url
    profile.contract_path = contract_path
    await db.commit()


async def _profile_out(profile: InstructorProfile, user: User) -> InstructorProfileOut:
    """Contract URLs are generated at query time from the stored paths (A2);
    the legacy *_url columns are only a fallback for pre-migration rows."""
    return InstructorProfileOut(
        user_id=profile.user_id,
        linkedin_url=user.linkedin_url,
        photo_url=await storage.resolve_url("profile_pictures", user.photo_path, user.photo_url),
        contract_url=await storage.resolve_url("contracts", profile.contract_path, profile.contract_url),
        signed_contract_url=await storage.resolve_url("contracts", profile.signed_contract_path, profile.signed_contract_url),
        contract_signed_at=profile.contract_signed_at,
    )


@router.get("/profile", response_model=InstructorProfileOut)
async def get_profile(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor_or_facilitator)):
    profile = await _get_or_create_profile(db, current_user.id)
    await _ensure_contract(db, profile, current_user)
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

    living_area = await _resolve_living_area(db, current_user)

    now = datetime.now(timezone.utc)
    try:
        pdf_bytes = await asyncio.to_thread(
            generate_contract_pdf,
            current_user.full_name,
            living_area,
            contract_date=now.strftime("%d %B %Y"),
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
