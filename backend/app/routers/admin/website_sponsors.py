from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.user import User
from app.models.website_sponsor import WebsiteSponsor
from app.schemas.website_sponsor import SponsorCreate, SponsorOut, SponsorUpdate

router = APIRouter(prefix="/website", tags=["admin-website-sponsors"])


@router.get("/sponsors", response_model=list[SponsorOut])
async def list_website_sponsors(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """All sponsors, including inactive (admin view)."""
    rows = (
        await db.execute(
            select(WebsiteSponsor).order_by(WebsiteSponsor.display_order, WebsiteSponsor.name)
        )
    ).scalars().all()
    return rows


@router.post("/sponsors", response_model=SponsorOut, status_code=status.HTTP_201_CREATED)
async def create_website_sponsor(
    body: SponsorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    row = WebsiteSponsor(**body.model_dump())
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/sponsors/{sponsor_id}", response_model=SponsorOut)
async def update_website_sponsor(
    sponsor_id: UUID,
    body: SponsorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    row = (await db.execute(select(WebsiteSponsor).where(WebsiteSponsor.id == sponsor_id))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/sponsors/{sponsor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_website_sponsor(
    sponsor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    row = (await db.execute(select(WebsiteSponsor).where(WebsiteSponsor.id == sponsor_id))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    await db.delete(row)
    await db.commit()
    return None
