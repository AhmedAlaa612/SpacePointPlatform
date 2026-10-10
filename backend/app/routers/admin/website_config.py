from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
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
    return row


@router.get("/config", response_model=WebsiteConfigOut)
async def get_website_config(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    return await _get_or_seed(db)


@router.put("/config", response_model=WebsiteConfigOut)
async def update_website_config(
    body: WebsiteConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    row = await _get_or_seed(db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row
