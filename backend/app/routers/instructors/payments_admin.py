import asyncio
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_admin
from app.core.config import settings
from app.db.session import get_db
from app.models.certificate import Certificate
from app.models.enums import CertificateType, PaymentLetterStatus
from app.models.instructors.payment import (
    InstructorBankDetails,
    PaymentAddon,
    PaymentBatch,
    PaymentLetter,
    PaymentSession,
)
from app.services.settings import get_portal_setting as _get_setting
from app.models.user import User
from app.schemas.instructors.payment import (
    BulkImportPreviewOut,
    CertificateCreate,
    CertificateOut,
    PaymentAddonCreate,
    PaymentBatchCreate,
    PaymentBatchOut,
    PaymentLetterCreate,
    PaymentLetterOut,
    PaymentSessionCreate,
)
from app.services import storage
from app.services.documents.certificate import generate_completion_certificate_pdf
from app.services.documents.payment_letter import (
    generate_excel_template,
    generate_payment_letter_pdf,
    parse_excel_bulk_import,
)
from app.services.email import send_payment_letter_ready_email, send_workshop_certificate_ready_email

router = APIRouter(prefix="/admin/payments", tags=["instructors-payments-admin"])

logger = logging.getLogger("payments_admin")


async def _letter_with_children(db: AsyncSession, letter: PaymentLetter) -> PaymentLetterOut:
    sessions = (await db.execute(
        select(PaymentSession).where(PaymentSession.payment_letter_id == letter.id).order_by(PaymentSession.sort_order)
    )).scalars().all()
    addons = (await db.execute(
        select(PaymentAddon).where(PaymentAddon.payment_letter_id == letter.id).order_by(PaymentAddon.sort_order)
    )).scalars().all()
    instructor = (await db.execute(select(User.full_name).where(User.id == letter.instructor_user_id))).scalar_one_or_none()
    out = PaymentLetterOut.model_validate(letter, from_attributes=True)
    out.instructor_name = instructor
    out.sessions = sessions
    out.addons = addons
    out.pdf_url = await storage.resolve_url("payment-letters", letter.pdf_path, letter.pdf_url)
    out.signed_pdf_url = await storage.resolve_url("payment-letters", letter.signed_pdf_path, letter.signed_pdf_url)
    return out


# ── Batches ────────────────────────────────────────────────────

@router.get("/batches", response_model=list[PaymentBatchOut])
async def list_batches(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    batches = (await db.execute(select(PaymentBatch).order_by(PaymentBatch.created_at.desc()))).scalars().all()
    counts = (await db.execute(
        select(PaymentLetter.batch_id, func.count()).group_by(PaymentLetter.batch_id)
    )).all()
    count_by_batch = {b: c for b, c in counts}
    return [
        PaymentBatchOut(id=b.id, name=b.name, description=b.description, letter_count=count_by_batch.get(b.id, 0))
        for b in batches
    ]


@router.post("/batches", response_model=PaymentBatchOut, status_code=201)
async def create_batch(
    body: PaymentBatchCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    batch = PaymentBatch(name=body.name, description=body.description, created_by_admin_id=current_user.id)
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    return PaymentBatchOut(id=batch.id, name=batch.name, description=batch.description, letter_count=0)


@router.delete("/batches/{batch_id}")
async def delete_batch(
    batch_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    batch = (await db.execute(select(PaymentBatch).where(PaymentBatch.id == batch_id))).scalars().first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    await db.delete(batch)
    await db.commit()
    return {"status": "deleted"}


# ── Letters ────────────────────────────────────────────────────

@router.get("/letters", response_model=list[PaymentLetterOut])
async def list_letters(
    batch_id: uuid.UUID | None = None, status: PaymentLetterStatus | None = None,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin),
):
    q = select(PaymentLetter).order_by(PaymentLetter.created_at.desc())
    if batch_id:
        q = q.where(PaymentLetter.batch_id == batch_id)
    if status:
        q = q.where(PaymentLetter.status == status)
    letters = (await db.execute(q)).scalars().all()
    return [await _letter_with_children(db, l) for l in letters]


@router.get("/letters/{letter_id}", response_model=PaymentLetterOut)
async def get_letter(
    letter_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    letter = (await db.execute(select(PaymentLetter).where(PaymentLetter.id == letter_id))).scalars().first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    return await _letter_with_children(db, letter)


@router.post("/letters", response_model=PaymentLetterOut, status_code=201)
async def create_letter(
    body: PaymentLetterCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    letter = PaymentLetter(
        instructor_user_id=body.instructor_user_id, batch_id=body.batch_id,
        letter_date=body.letter_date or datetime.now(timezone.utc).strftime("%d/%m/%Y"), reference=body.reference,
    )
    db.add(letter)
    await db.commit()
    await db.refresh(letter)
    return await _letter_with_children(db, letter)


@router.delete("/letters/{letter_id}")
async def delete_letter(
    letter_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    letter = (await db.execute(select(PaymentLetter).where(PaymentLetter.id == letter_id))).scalars().first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    await db.delete(letter)
    await db.commit()
    return {"status": "deleted"}


@router.post("/letters/{letter_id}/sessions", response_model=PaymentLetterOut, status_code=201)
async def add_session(
    letter_id: uuid.UUID, body: PaymentSessionCreate,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin),
):
    letter = (await db.execute(select(PaymentLetter).where(PaymentLetter.id == letter_id))).scalars().first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    db.add(PaymentSession(payment_letter_id=letter_id, **body.model_dump()))
    await db.commit()
    return await _letter_with_children(db, letter)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    session_row = (await db.execute(select(PaymentSession).where(PaymentSession.id == session_id))).scalars().first()
    if not session_row:
        raise HTTPException(status_code=404, detail="Session not found")
    await db.delete(session_row)
    await db.commit()
    return {"status": "deleted"}


@router.post("/letters/{letter_id}/addons", response_model=PaymentLetterOut, status_code=201)
async def add_addon(
    letter_id: uuid.UUID, body: PaymentAddonCreate,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin),
):
    letter = (await db.execute(select(PaymentLetter).where(PaymentLetter.id == letter_id))).scalars().first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    db.add(PaymentAddon(payment_letter_id=letter_id, **body.model_dump()))
    await db.commit()
    return await _letter_with_children(db, letter)


@router.delete("/addons/{addon_id}")
async def delete_addon(
    addon_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    addon = (await db.execute(select(PaymentAddon).where(PaymentAddon.id == addon_id))).scalars().first()
    if not addon:
        raise HTTPException(status_code=404, detail="Add-on not found")
    await db.delete(addon)
    await db.commit()
    return {"status": "deleted"}


@router.post("/letters/{letter_id}/generate-pdf", response_model=PaymentLetterOut)
async def generate_pdf(
    letter_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    letter = (await db.execute(select(PaymentLetter).where(PaymentLetter.id == letter_id))).scalars().first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    instructor = (await db.execute(select(User).where(User.id == letter.instructor_user_id))).scalars().first()
    sessions = (await db.execute(select(PaymentSession).where(PaymentSession.payment_letter_id == letter_id))).scalars().all()
    addons = (await db.execute(select(PaymentAddon).where(PaymentAddon.payment_letter_id == letter_id))).scalars().all()
    bank = (await db.execute(select(InstructorBankDetails).where(InstructorBankDetails.user_id == letter.instructor_user_id))).scalars().first()

    admin_signature_bytes = None
    sig_url = await _get_setting(db, "admin_signature_url", "")
    if sig_url:
        try:
            admin_signature_bytes = await storage.download_file("instructor-documents", "settings/admin_signature.png")
        except Exception as e:
            print(f"Error downloading admin signature: {e}")

    try:
        pdf_bytes = await asyncio.to_thread(
            generate_payment_letter_pdf,
            instructor_name=instructor.full_name, reference=letter.reference, letter_date=letter.letter_date or "",
            sessions=[{"session_date": s.session_date, "workshop_description": s.workshop_description, "role": s.role.value,
                       "location": s.location, "duration_hours": s.duration_hours, "compensation_aed": s.compensation_aed} for s in sessions],
            addons=[{"description": a.description, "amount_aed": a.amount_aed, "notes": a.notes} for a in addons],
            bank={"account_holder_name": bank.account_holder_name, "bank_name": bank.bank_name, "iban": bank.iban,
                  "swift_bic": bank.swift_bic} if bank else None,
            admin_signatory_name=await _get_setting(db, "admin_signatory_name", settings.DEFAULT_SIGNATORY_NAME),
            admin_signatory_title=await _get_setting(db, "admin_signatory_title", settings.DEFAULT_SIGNATORY_TITLE),
            admin_signature_bytes=admin_signature_bytes,
            instructor_signature_b64=letter.instructor_signature_data,
            signed_date=letter.signed_at.strftime("%d/%m/%Y") if letter.signed_at else None,
        )
        letter_pdf_path = f"{letter.id}/letter.pdf"
        letter.pdf_url = await storage.upload_file("payment-letters", letter_pdf_path, pdf_bytes, "application/pdf")
        letter.pdf_path = letter_pdf_path
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"PDF generation or upload failed: {str(e)}"
        )
    await db.commit()
    return await _letter_with_children(db, letter)


@router.post("/letters/{letter_id}/publish", response_model=PaymentLetterOut)
async def publish_letter(
    letter_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    letter = (await db.execute(select(PaymentLetter).where(PaymentLetter.id == letter_id))).scalars().first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    letter.is_published = True
    letter.status = PaymentLetterStatus.published
    instructor = (await db.execute(select(User).where(User.id == letter.instructor_user_id))).scalars().first()
    await send_payment_letter_ready_email(instructor.email, instructor.full_name)
    await db.commit()
    return await _letter_with_children(db, letter)


@router.post("/letters/{letter_id}/mark-paid", response_model=PaymentLetterOut)
async def mark_paid(
    letter_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    letter = (await db.execute(select(PaymentLetter).where(PaymentLetter.id == letter_id))).scalars().first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    letter.status = PaymentLetterStatus.paid
    await db.commit()
    return await _letter_with_children(db, letter)


# ── Bulk import ────────────────────────────────────────────────

@router.post("/bulk-import/preview", response_model=BulkImportPreviewOut)
async def bulk_import_preview(
    file: UploadFile, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    data = await file.read()
    parsed = parse_excel_bulk_import(data)
    emails = list(parsed["instructors"].keys())
    matched = (await db.execute(select(User.email).where(User.email.in_(emails), User.roles.any("instructor")))).scalars().all()
    unmatched = [e for e in emails if e not in matched]
    return BulkImportPreviewOut(
        instructor_count=len(parsed["instructors"]),
        session_count=sum(len(i["sessions"]) for i in parsed["instructors"].values()),
        addon_count=sum(len(i["addons"]) for i in parsed["instructors"].values()),
        unmatched_emails=unmatched, errors=parsed["errors"],
    )


@router.post("/bulk-import/confirm")
async def bulk_import_confirm(
    file: UploadFile, batch_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin),
):
    data = await file.read()
    parsed = parse_excel_bulk_import(data)
    created_letters = 0
    for email, content in parsed["instructors"].items():
        instructor = (await db.execute(select(User).where(User.email == email, User.roles.any("instructor")))).scalars().first()
        if not instructor:
            continue
        letter = PaymentLetter(
            instructor_user_id=instructor.id, batch_id=batch_id,
            letter_date=datetime.now(timezone.utc).strftime("%d/%m/%Y"),
        )
        db.add(letter)
        await db.flush()
        for i, s in enumerate(content["sessions"], 1):
            db.add(PaymentSession(payment_letter_id=letter.id, sort_order=i, **s))
        for i, a in enumerate(content["addons"], 1):
            db.add(PaymentAddon(payment_letter_id=letter.id, sort_order=i, **a))
        created_letters += 1
    await db.commit()
    return {"created_letters": created_letters, "errors": parsed["errors"]}


@router.get("/bulk-import/template")
async def bulk_import_template(current_user: User = Depends(require_admin)):
    content = generate_excel_template()
    return Response(
        content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=bulk_import_template.xlsx"},
    )


@router.get("/instructors")
async def payments_instructor_dropdown(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    rows = (await db.execute(select(User.id, User.full_name, User.email).where(User.roles.any("instructor")))).all()
    return [{"id": str(r.id), "full_name": r.full_name, "email": r.email} for r in rows]


# ── Certificates ───────────────────────────────────────────────

@router.get("/certificates", response_model=list[CertificateOut])
async def list_certificates(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    rows = (await db.execute(
        select(Certificate, User.full_name, User.email)
        .join(User, User.id == Certificate.user_id)
        .order_by(Certificate.generated_at.desc())
    )).all()
    return [
        CertificateOut(
            id=c.id, user_id=c.user_id, instructor_name=name, instructor_email=email, type=c.type.value,
            workshop_name=c.workshop_name, workshop_date=c.workshop_date, location=c.location,
            file_url=await storage.resolve_url(c.bucket, c.file_path, c.file_url),
        )
        for c, name, email in rows
    ]


@router.post("/certificates", response_model=CertificateOut, status_code=201)
async def create_certificate(
    body: CertificateCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """Manually issue a workshop-delivery certificate of achievement — the
    ad-hoc counterpart to the auto-issued instructor_completion cert fired on
    application approval (routers/instructors/admin.py `approved` branch)."""
    instructor = (await db.execute(
        select(User).where(User.id == body.instructor_user_id, User.roles.any("instructor"))
    )).scalars().first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found")

    body_text = f"For successfully delivering<br/>{body.workshop_name}<br/>{body.workshop_date} — {body.location}"
    cert_bytes = await asyncio.to_thread(generate_completion_certificate_pdf, instructor.full_name, body_text)
    cert_id = uuid.uuid4()
    cert_bucket, cert_path = "certificates", f"{instructor.id}/workshop_{cert_id}.pdf"
    cert_url = await storage.upload_file(cert_bucket, cert_path, cert_bytes, "application/pdf")

    certificate = Certificate(
        id=cert_id, user_id=instructor.id, type=CertificateType.workshop_delivery,
        workshop_name=body.workshop_name, workshop_date=body.workshop_date, location=body.location,
        generated_by=current_user.id, file_url=cert_url, bucket=cert_bucket, file_path=cert_path,
    )
    db.add(certificate)
    await db.commit()

    if body.send_email:
        await send_workshop_certificate_ready_email(
            instructor.email, instructor.full_name, body.workshop_name, cert_bytes
        )

    return CertificateOut(
        id=certificate.id, user_id=certificate.user_id, instructor_name=instructor.full_name,
        instructor_email=instructor.email, type=certificate.type.value,
        workshop_name=certificate.workshop_name, workshop_date=certificate.workshop_date,
        location=certificate.location,
        file_url=await storage.resolve_url(certificate.bucket, certificate.file_path, certificate.file_url),
    )


@router.delete("/certificates/{certificate_id}")
async def delete_certificate(
    certificate_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    certificate = (await db.execute(select(Certificate).where(Certificate.id == certificate_id))).scalars().first()
    if not certificate:
        raise HTTPException(status_code=404, detail="Certificate not found")

    if certificate.bucket and certificate.file_path:
        try:
            await storage.delete_file(certificate.bucket, certificate.file_path)
        except Exception as e:
            logger.warning("certificate file delete failed (%s/%s): %s", certificate.bucket, certificate.file_path, e)

    await db.delete(certificate)
    await db.commit()
    return {"status": "deleted"}
