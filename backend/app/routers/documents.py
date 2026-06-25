"""Shared documents router (PLAN §4.5/§8.2/§9.4) — top-level, not nested under
any one domain, since recommendation letters apply to any role. Same mounting
pattern as routers/notifications.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.config import settings
from app.core.dependencies import get_current_active_user, require_admin
from app.db.session import get_db
from app.models.certificate import Certificate
from app.models.instructors.payment import PortalSetting
from app.models.intern_letter import InternLetter
from app.models.recommendation_letter import RecommendationLetter
from app.models.user import User
from app.schemas.documents import (
    InternLetterOut,
    MyDocumentsOut,
    RecommendationLetterCreate,
    RecommendationLetterOut,
)
from app.schemas.instructors.payment import CertificateOut
from app.services import storage
from app.services.documents.recommendation import generate_recommendation_letter_pdf
from app.services.email import send_recommendation_letter_email

router = APIRouter(prefix="/documents", tags=["documents"])


async def _get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    row = (await db.execute(select(PortalSetting).where(PortalSetting.key == key))).scalars().first()
    return row.value if row and row.value else default


@router.get("/me", response_model=MyDocumentsOut)
async def my_documents(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_active_user)
):
    certs = (await db.execute(
        select(Certificate).where(Certificate.user_id == current_user.id).order_by(Certificate.generated_at.desc())
    )).scalars().all()
    rec_letters = (await db.execute(
        select(RecommendationLetter).where(RecommendationLetter.user_id == current_user.id)
        .order_by(RecommendationLetter.generated_at.desc())
    )).scalars().all()
    intern_letters = (await db.execute(
        select(InternLetter).where(InternLetter.user_id == current_user.id)
        .order_by(InternLetter.generated_at.desc())
    )).scalars().all()

    return MyDocumentsOut(
        certificates=[
            CertificateOut(
                id=c.id, user_id=c.user_id, type=c.type.value,
                workshop_name=c.workshop_name, workshop_date=c.workshop_date, location=c.location,
                file_url=c.file_url,
            )
            for c in certs
        ],
        recommendation_letters=rec_letters,
        intern_letters=intern_letters,
    )


@router.post("/recommendation-letters", response_model=RecommendationLetterOut)
async def create_recommendation_letter(
    body: RecommendationLetterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = (await db.execute(select(User).where(User.id == body.user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    signatory_name = body.signatory_name or await _get_setting(
        db, "admin_signatory_name", settings.DEFAULT_SIGNATORY_NAME
    )
    signatory_title = body.signatory_title or await _get_setting(
        db, "admin_signatory_title", settings.DEFAULT_SIGNATORY_TITLE
    )

    pdf_bytes = generate_recommendation_letter_pdf(
        user.full_name, body.recommendation_text, signatory_name, signatory_title,
    )
    file_url = await storage.upload_file(
        "recommendation-letters", f"{user.id}/{uuid.uuid4()}.pdf", pdf_bytes, "application/pdf"
    )

    letter = RecommendationLetter(
        user_id=user.id, generated_by=current_user.id,
        signatory_name=signatory_name, signatory_title=signatory_title, file_url=file_url,
    )
    db.add(letter)
    await db.commit()

    await send_recommendation_letter_email(user.email, user.full_name)
    return letter


@router.get("/recommendation-letters", response_model=list[RecommendationLetterOut])
async def list_recommendation_letters(
    user_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    rows = (await db.execute(
        select(RecommendationLetter).where(RecommendationLetter.user_id == user_id)
        .order_by(RecommendationLetter.generated_at.desc())
    )).scalars().all()
    return rows
