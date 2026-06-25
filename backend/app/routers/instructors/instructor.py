import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_instructor
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.id_card import IdCard
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
)
from app.services import storage
from app.services.documents.id_card import generate_id_card

router = APIRouter(tags=["instructors-instructor"])


async def _get_or_create_profile(db: AsyncSession, user_id: uuid.UUID) -> InstructorProfile:
    profile = (await db.execute(select(InstructorProfile).where(InstructorProfile.user_id == user_id))).scalars().first()
    if not profile:
        profile = InstructorProfile(user_id=user_id)
        db.add(profile)
        await db.flush()
    return profile


@router.get("/profile", response_model=InstructorProfileOut)
async def get_profile(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)):
    return await _get_or_create_profile(db, current_user.id)


@router.put("/profile", response_model=InstructorProfileOut)
async def update_profile(
    body: InstructorProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor),
):
    profile = await _get_or_create_profile(db, current_user.id)
    if body.linkedin_url is not None:
        profile.linkedin_url = body.linkedin_url
    await db.commit()
    await db.refresh(profile)
    return profile


@router.get("/id-card", response_model=IdCardOut | None)
async def get_id_card(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)):
    return (await db.execute(
        select(IdCard).where(IdCard.user_id == current_user.id, IdCard.role == "instructor")
    )).scalars().first()


@router.post("/id-card", response_model=IdCardOut)
async def generate_my_id_card(
    photo: UploadFile,
    linkedin_url: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor),
):
    photo_bytes = await photo.read()
    profile = await _get_or_create_profile(db, current_user.id)
    if linkedin_url:
        profile.linkedin_url = linkedin_url

    photo_url = await storage.upload_file(
        "instructor-photos", f"{current_user.id}{_ext(photo.filename)}", photo_bytes, photo.content_type or "image/jpeg"
    )
    profile.photo_url = photo_url

    card = await generate_id_card(
        db, current_user.id, UserRole.instructor,
        current_user.full_name, photo_bytes, linkedin_url or profile.linkedin_url,
    )
    await db.commit()
    await db.refresh(card)
    return card


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


# ── Personal document vault ───────────────────────────────────

@router.get("/documents", response_model=list[InstructorDocumentOut])
async def list_documents(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)):
    rows = (await db.execute(
        select(InstructorDocument).where(InstructorDocument.user_id == current_user.id).order_by(InstructorDocument.uploaded_at.desc())
    )).scalars().all()
    return list(rows)


@router.post("/documents", response_model=InstructorDocumentOut, status_code=201)
async def upload_document(
    document_type: str,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_instructor),
):
    data = await file.read()
    path = f"{current_user.id}_{document_type}_{int(datetime.now(timezone.utc).timestamp())}{_ext(file.filename)}"
    file_url = await storage.upload_file("instructor-documents", path, data, file.content_type or "application/octet-stream")
    doc = InstructorDocument(user_id=current_user.id, document_type=document_type, file_url=file_url)
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_instructor)
):
    doc = (await db.execute(
        select(InstructorDocument).where(InstructorDocument.id == doc_id, InstructorDocument.user_id == current_user.id)
    )).scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)
    await db.commit()
    return {"status": "deleted"}
