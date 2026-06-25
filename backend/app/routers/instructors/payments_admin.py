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
from app.models.enums import PaymentLetterStatus
from app.models.instructors.payment import (
    InstructorBankDetails,
    PaymentAddon,
    PaymentBatch,
    PaymentLetter,
    PaymentSession,
    PortalSetting,
)
from app.models.user import User
from app.schemas.instructors.payment import (
    BulkImportPreviewOut,
    CertificateOut,
    PaymentAddonCreate,
    PaymentBatchCreate,
    PaymentBatchOut,
    PaymentLetterCreate,
    PaymentLetterOut,
    PaymentSessionCreate,
)
from app.services import storage
from app.services.documents.payment_letter import (
    generate_excel_template,
    generate_payment_letter_pdf,
    parse_excel_bulk_import,
)
from app.services.email import send_payment_letter_ready_email

router = APIRouter(prefix="/admin/payments", tags=["instructors-payments-admin"])


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


async def _get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    row = (await db.execute(select(PortalSetting).where(PortalSetting.key == key))).scalars().first()
    return row.value if row and row.value else default


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

    pdf_bytes = generate_payment_letter_pdf(
        instructor_name=instructor.full_name, reference=letter.reference, letter_date=letter.letter_date or "",
        sessions=[{"session_date": s.session_date, "workshop_description": s.workshop_description, "role": s.role.value,
                   "location": s.location, "duration_hours": s.duration_hours, "compensation_aed": s.compensation_aed} for s in sessions],
        addons=[{"description": a.description, "amount_aed": a.amount_aed, "notes": a.notes} for a in addons],
        bank={"account_holder_name": bank.account_holder_name, "bank_name": bank.bank_name, "iban": bank.iban,
              "swift_bic": bank.swift_bic} if bank else None,
        admin_signatory_name=await _get_setting(db, "admin_signatory_name", settings.DEFAULT_SIGNATORY_NAME),
        instructor_signature_b64=letter.instructor_signature_data,
        signed_date=letter.signed_at.strftime("%d/%m/%Y") if letter.signed_at else None,
    )
    letter.pdf_url = await storage.upload_file("payment-letters", f"{letter.id}/letter.pdf", pdf_bytes, "application/pdf")
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
        select(Certificate, User.full_name)
        .join(User, User.id == Certificate.user_id)
        .order_by(Certificate.generated_at.desc())
    )).all()
    return [
        CertificateOut(
            id=c.id, user_id=c.user_id, instructor_name=name, type=c.type.value,
            workshop_name=c.workshop_name, workshop_date=c.workshop_date, location=c.location, file_url=c.file_url,
        )
        for c, name in rows
    ]
