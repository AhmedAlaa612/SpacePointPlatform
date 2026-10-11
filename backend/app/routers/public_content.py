"""Public website content endpoints — no auth required.

Step 4 — FAQs, Media Coverage & Monthly Newsletters: the marketing site
reads active FAQs, press clippings, and newsletter issues here, and
collects newsletter subscribers (deduplicated into website_leads).
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.website_config import WebsiteConfig
from app.models.website_faq import WebsiteFaq
from app.models.website_media import MediaClipping
from app.models.website_newsletter import Newsletter, WebsiteLead
from app.schemas.website_faq import FaqOut
from app.schemas.website_media import MediaClippingOut
from app.schemas.website_newsletter import (
    LeadCreateIn,
    LeadOut,
    NewsletterOut,
    NewsletterSubscribeIn,
)
from app.services.email import send_email

router = APIRouter(prefix="/public", tags=["public-content"])


async def _active_list(db: AsyncSession, model, out_model):
    """Active rows ordered for display; unmigrated (fresh table) reads as
    an empty list rather than a 500 so the marketing site's fallback
    content stays in charge."""
    try:
        rows = (
            await db.execute(
                select(model)
                .where(model.is_active.is_(True))
                .order_by(model.display_order, model.created_at)
            )
        ).scalars().all()
    except Exception:
        return []
    return [out_model.model_validate(r) for r in rows]


@router.get("/faqs", response_model=list[FaqOut])
async def list_public_faqs(db: AsyncSession = Depends(get_db)):
    return await _active_list(db, WebsiteFaq, FaqOut)


@router.get("/media", response_model=list[MediaClippingOut])
async def list_public_media(db: AsyncSession = Depends(get_db)):
    return await _active_list(db, MediaClipping, MediaClippingOut)


@router.get("/newsletters", response_model=list[NewsletterOut])
async def list_public_newsletters(db: AsyncSession = Depends(get_db)):
    return await _active_list(db, Newsletter, NewsletterOut)


@router.post("/newsletter/subscribe", response_model=LeadOut)
async def subscribe_newsletter(body: NewsletterSubscribeIn, db: AsyncSession = Depends(get_db)):
    """Idempotent subscribe: a repeat signup for the same email returns
    the existing row instead of creating a duplicate."""
    email = body.email.strip().lower()
    existing = (
        await db.execute(
            select(WebsiteLead).where(
                func.lower(WebsiteLead.email) == email,
                WebsiteLead.lead_type == "newsletter",
            )
        )
    ).scalars().first()
    if existing is not None:
        return existing
    row = WebsiteLead(email=email, lead_type="newsletter", status="new")
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/leads")
async def create_public_lead(body: LeadCreateIn, db: AsyncSession = Depends(get_db)):
    """Capture a public contact/workshop inquiry into website_leads and forward
    it by email to the configured SpacePoint support address (info@spacepoint.ae)."""
    email = body.email.strip().lower()
    lead_type = (body.lead_type or "inquiry").strip()[:32]
    row = WebsiteLead(email=email, lead_type=lead_type, status="new")
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # Resolve recipient email from WebsiteConfig (defaults to info@spacepoint.ae)
    cfg = (await db.execute(select(WebsiteConfig).where(WebsiteConfig.id == 1))).scalars().first()
    recipient = (cfg.contact_email if cfg and cfg.contact_email else "info@spacepoint.ae").strip()

    msg_text = ""
    if isinstance(body.details, dict):
        msg_text = str(body.details.get("message") or "")

    subject = f"[SpacePoint Website] {body.program_interest or 'New Inquiry'} — {body.contact_name or email}"
    lines = [
        f"New website {lead_type} received:",
        "",
        f"Name: {body.contact_name or '—'}",
        f"Email: {email}",
        f"Phone: {body.phone or '—'}",
        f"Organization: {body.organization_name or '—'}",
        f"Interest: {body.program_interest or '—'}",
        "",
        "Message:",
        msg_text or "—",
    ]
    try:
        await send_email(to=recipient, subject=subject, body="\n".join(lines), html=False)
    except Exception:
        pass

    return {"success": True, "message": "Inquiry received", "id": str(row.id)}
