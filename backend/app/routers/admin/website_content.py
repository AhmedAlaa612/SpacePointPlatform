from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_website_admin
from app.db.session import get_db
from app.models.user import User
from app.models.website_faq import WebsiteFaq
from app.models.website_media import MediaClipping
from app.models.website_newsletter import Newsletter, WebsiteLead
from app.schemas.website_faq import FaqCreate, FaqOut, FaqUpdate
from app.schemas.website_media import MediaClippingCreate, MediaClippingOut, MediaClippingUpdate
from app.schemas.website_newsletter import LeadOut, NewsletterCreate, NewsletterOut, NewsletterUpdate

router = APIRouter(prefix="/website", tags=["admin-website-content"])


def _not_found(entity: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{entity} not found")


async def _ordered_list(db: AsyncSession, model):
    return (
        await db.execute(select(model).order_by(model.display_order, model.created_at))
    ).scalars().all()


# ── FAQs ──────────────────────────────────────────────────────────────────


@router.get("/faqs", response_model=list[FaqOut])
async def list_website_faqs(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _ordered_list(db, WebsiteFaq)


@router.post("/faqs", response_model=FaqOut, status_code=status.HTTP_201_CREATED)
async def create_website_faq(
    body: FaqCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = WebsiteFaq(**body.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/faqs/{faq_id}", response_model=FaqOut)
async def update_website_faq(
    faq_id: UUID,
    body: FaqUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = (await db.execute(select(WebsiteFaq).where(WebsiteFaq.id == faq_id))).scalars().first()
    if row is None:
        raise _not_found("FAQ")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/faqs/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_website_faq(
    faq_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = (await db.execute(select(WebsiteFaq).where(WebsiteFaq.id == faq_id))).scalars().first()
    if row is None:
        raise _not_found("FAQ")
    await db.delete(row)
    await db.commit()
    return None


# ── Media clippings ───────────────────────────────────────────────────────


@router.get("/media", response_model=list[MediaClippingOut])
async def list_website_media(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _ordered_list(db, MediaClipping)


@router.post("/media", response_model=MediaClippingOut, status_code=status.HTTP_201_CREATED)
async def create_website_media(
    body: MediaClippingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = MediaClipping(**body.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/media/{media_id}", response_model=MediaClippingOut)
async def update_website_media(
    media_id: UUID,
    body: MediaClippingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = (await db.execute(select(MediaClipping).where(MediaClipping.id == media_id))).scalars().first()
    if row is None:
        raise _not_found("Media clipping")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_website_media(
    media_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = (await db.execute(select(MediaClipping).where(MediaClipping.id == media_id))).scalars().first()
    if row is None:
        raise _not_found("Media clipping")
    await db.delete(row)
    await db.commit()
    return None


# ── Newsletters ───────────────────────────────────────────────────────────


@router.get("/newsletters", response_model=list[NewsletterOut])
async def list_website_newsletters(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _ordered_list(db, Newsletter)


@router.post("/newsletters", response_model=NewsletterOut, status_code=status.HTTP_201_CREATED)
async def create_website_newsletter(
    body: NewsletterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = Newsletter(**body.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/newsletters/{newsletter_id}", response_model=NewsletterOut)
async def update_website_newsletter(
    newsletter_id: UUID,
    body: NewsletterUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = (await db.execute(select(Newsletter).where(Newsletter.id == newsletter_id))).scalars().first()
    if row is None:
        raise _not_found("Newsletter")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/newsletters/{newsletter_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_website_newsletter(
    newsletter_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = (await db.execute(select(Newsletter).where(Newsletter.id == newsletter_id))).scalars().first()
    if row is None:
        raise _not_found("Newsletter")
    await db.delete(row)
    await db.commit()
    return None


# ── Leads ─────────────────────────────────────────────────────────────────


@router.get("/leads", response_model=list[LeadOut])
async def list_website_leads(
    type: str = Query(default="newsletter"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    rows = (
        await db.execute(
            select(WebsiteLead)
            .where(WebsiteLead.lead_type == type)
            .order_by(WebsiteLead.created_at.desc())
        )
    ).scalars().all()
    return rows
