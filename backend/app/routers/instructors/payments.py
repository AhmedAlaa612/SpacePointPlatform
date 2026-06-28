import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.dependencies import require_instructor
from app.db.session import get_db
from app.models.certificate import Certificate
from app.models.enums import CertificateType, PaymentLetterStatus
from app.models.instructors.payment import InstructorBankDetails, PaymentAddon, PaymentLetter, PaymentSession
from app.services.settings import get_portal_setting as _get_setting
from app.models.user import User
from app.schemas.instructors.payment import PaymentLetterOut, PaymentSummaryOut, SignLetterRequest
from xml.sax.saxutils import escape

from app.models.document_template import DocumentTemplate
from app.services import storage
from app.services.documents.certificate import generate_completion_certificate_pdf
from app.services.documents.payment_letter import generate_payment_letter_pdf
from app.services.email import (
    send_certificates_email,
    send_payment_signed_notification_email,
)
from app.services.notification import create_notification as notify

router = APIRouter(prefix="/payments", tags=["instructors-payments"])


async def _letter_with_children(db: AsyncSession, letter: PaymentLetter) -> PaymentLetterOut:
    sessions = (await db.execute(
        select(PaymentSession).where(PaymentSession.payment_letter_id == letter.id).order_by(PaymentSession.sort_order)
    )).scalars().all()
    addons = (await db.execute(
        select(PaymentAddon).where(PaymentAddon.payment_letter_id == letter.id).order_by(PaymentAddon.sort_order)
    )).scalars().all()
    out = PaymentLetterOut.model_validate(letter, from_attributes=True)
    out.sessions = sessions
    out.addons = addons
    return out


@router.get("/letters", response_model=list[PaymentLetterOut])
async def list_my_letters(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)):
    letters = (await db.execute(
        select(PaymentLetter).where(
            PaymentLetter.instructor_user_id == current_user.id, PaymentLetter.is_published.is_(True)
        ).order_by(PaymentLetter.created_at.desc())
    )).scalars().all()
    return [await _letter_with_children(db, l) for l in letters]


@router.get("/letters/{letter_id}", response_model=PaymentLetterOut)
async def get_letter(
    letter_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)
):
    letter = (await db.execute(
        select(PaymentLetter).where(PaymentLetter.id == letter_id, PaymentLetter.instructor_user_id == current_user.id)
    )).scalars().first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    return await _letter_with_children(db, letter)


@router.post("/letters/{letter_id}/sign", response_model=PaymentLetterOut)
async def sign_letter(
    letter_id: uuid.UUID,
    body: SignLetterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor),
):
    letter = (await db.execute(
        select(PaymentLetter).where(
            PaymentLetter.id == letter_id,
            PaymentLetter.instructor_user_id == current_user.id,
            PaymentLetter.is_published.is_(True),
        )
    )).scalars().first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    if letter.status == PaymentLetterStatus.signed:
        raise HTTPException(status_code=400, detail="Letter already signed")

    sessions = (await db.execute(
        select(PaymentSession).where(PaymentSession.payment_letter_id == letter.id).order_by(PaymentSession.sort_order)
    )).scalars().all()
    addons = (await db.execute(
        select(PaymentAddon).where(PaymentAddon.payment_letter_id == letter.id).order_by(PaymentAddon.sort_order)
    )).scalars().all()
    bank = (await db.execute(
        select(InstructorBankDetails).where(InstructorBankDetails.user_id == current_user.id)
    )).scalars().first()

    now = datetime.now(timezone.utc)
    letter.instructor_signature_data = body.signature
    letter.signed_at = now
    letter.status = PaymentLetterStatus.signed

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
            instructor_name=current_user.full_name,
            reference=letter.reference,
            letter_date=letter.letter_date or now.strftime("%d/%m/%Y"),
            sessions=[{
                "session_date": s.session_date, "workshop_description": s.workshop_description,
                "role": s.role.value, "location": s.location, "duration_hours": s.duration_hours,
                "compensation_aed": s.compensation_aed,
            } for s in sessions],
            addons=[{"description": a.description, "amount_aed": a.amount_aed, "notes": a.notes} for a in addons],
            bank={
                "account_holder_name": bank.account_holder_name, "bank_name": bank.bank_name,
                "iban": bank.iban, "swift_bic": bank.swift_bic,
            } if bank else None,
            admin_signatory_name=await _get_setting(db, "admin_signatory_name", settings.DEFAULT_SIGNATORY_NAME),
            admin_signatory_title=await _get_setting(db, "admin_signatory_title", settings.DEFAULT_SIGNATORY_TITLE),
            admin_signature_bytes=admin_signature_bytes,
            instructor_signature_b64=body.signature,
            signed_date=now.strftime("%d/%m/%Y"),
        )
        letter.signed_pdf_url = await storage.upload_file(
            "payment-letters", f"{letter.id}/signed.pdf", pdf_bytes, "application/pdf"
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Signed PDF generation or upload failed: {str(e)}"
        )

    # One workshop-delivery certificate per session — rendered from the editable
    # `workshop_delivery` system template (seeded at startup) so admins can change
    # the wording without a code change.
    wd_template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == "workshop_delivery")
    )).scalars().first()
    cert_pdfs = []
    for s in sessions:
        body = (wd_template.body_text if wd_template else "") \
            .replace("{name}", escape(current_user.full_name)) \
            .replace("{workshop_name}", escape(s.workshop_description or "")) \
            .replace("{workshop_date}", escape(s.session_date or "")) \
            .replace("{location}", escape(s.location or ""))
        cert_bytes = await asyncio.to_thread(
            generate_completion_certificate_pdf, current_user.full_name, body, None,
        )
        cert_url = await storage.upload_file(
            "certificates", f"{current_user.id}/{s.id}.pdf", cert_bytes, "application/pdf"
        )
        db.add(Certificate(
            user_id=current_user.id, type=CertificateType.workshop_delivery, file_url=cert_url,
            payment_session_id=s.id, workshop_name=s.workshop_description,
            workshop_date=s.session_date, location=s.location,
        ))
        cert_pdfs.append((f"Certificate_{s.workshop_description}.pdf", cert_bytes))

    if cert_pdfs:
        await send_certificates_email(current_user.email, current_user.full_name, cert_pdfs)

    admins = (await db.execute(select(User).where(User.roles.any("admin")))).scalars().all()
    for admin in admins:
        await notify(db, admin.id, "Payment Letter Signed",
                     f"{current_user.full_name} signed their payment letter — review it in Payments.", type="instructor")
        await send_payment_signed_notification_email(admin.email, current_user.full_name)

    await db.commit()
    return await _letter_with_children(db, letter)


@router.get("/letters/{letter_id}/download")
async def download_letter(
    letter_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)
):
    letter = (await db.execute(
        select(PaymentLetter).where(PaymentLetter.id == letter_id, PaymentLetter.instructor_user_id == current_user.id)
    )).scalars().first()
    if not letter:
        raise HTTPException(status_code=404, detail="Letter not found")
    return {"url": letter.signed_pdf_url or letter.pdf_url}


@router.get("/summary", response_model=PaymentSummaryOut)
async def payment_summary(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)):
    letters = (await db.execute(
        select(PaymentLetter.id, PaymentLetter.status).where(
            PaymentLetter.instructor_user_id == current_user.id, PaymentLetter.is_published.is_(True)
        )
    )).all()
    letter_ids = [l.id for l in letters]
    pending = sum(1 for l in letters if l.status == PaymentLetterStatus.published)

    if not letter_ids:
        return PaymentSummaryOut(total_earned_aed=0, total_hours=0, total_sessions=0, pending_signature=pending)

    totals = (await db.execute(
        select(
            func.coalesce(func.sum(PaymentSession.compensation_aed), 0),
            func.coalesce(func.sum(PaymentSession.duration_hours), 0),
            func.count(PaymentSession.id),
        ).where(PaymentSession.payment_letter_id.in_(letter_ids))
    )).first()

    return PaymentSummaryOut(
        total_earned_aed=float(totals[0]), total_hours=float(totals[1]),
        total_sessions=int(totals[2]), pending_signature=pending,
    )
