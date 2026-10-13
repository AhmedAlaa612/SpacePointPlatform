from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_website_admin
from app.db.session import get_db
from app.models.user import User
from app.models.website_config import WebsiteConfig
from app.schemas.website_config import WebsiteConfigOut, WebsiteConfigUpdate

router = APIRouter(prefix="/website", tags=["admin-website-config"])


async def _get_or_seed(db: AsyncSession) -> WebsiteConfig:
    row = (await db.execute(select(WebsiteConfig).where(WebsiteConfig.id == 1))).scalars().first()
    if row is None:
        row = WebsiteConfig(id=1)
        db.add(row)
        await db.commit()
        await db.refresh(row)
    elif row.contact_phone == "+971 4 000 0000" and not row.social_linkedin:
        row.students_count = "2,700+"
        row.workshops_count = "40+"
        row.partners_count = "25"
        row.contact_phone = "+971 56 298 7005"
        row.contact_whatsapp = "+971 56 298 7005"
        row.office_address = "Sharjah Research, Technology and Innovation Park (SRTIP), Block B – Office B22-120, Sharjah, United Arab Emirates"
        row.social_linkedin = "https://www.linkedin.com/company/spacepointae/posts/?feedView=all"
        row.social_x = "https://www.tiktok.com/@spacepoint.ae"
        row.social_instagram = "https://www.instagram.com/spacepoint.ae"
        row.social_youtube = row.social_youtube or ""
        await db.commit()
        await db.refresh(row)
    return row


@router.get("/config", response_model=WebsiteConfigOut)
async def get_website_config(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
):
    return await _get_or_seed(db)


@router.put("/config", response_model=WebsiteConfigOut)
async def update_website_config(
    body: WebsiteConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = await _get_or_seed(db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row
