from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_website_admin
from app.db.session import get_db
from app.models.user import User
from app.models.website_sponsor import WebsiteSponsor
from app.schemas.website_sponsor import SponsorCreate, SponsorOut, SponsorUpdate

router = APIRouter(prefix="/website", tags=["admin-website-sponsors"])


async def _resequence_tier(db: AsyncSession, tier: str) -> None:
    """Ensure all sponsors in a given tier are sequentially numbered starting from 1 with no duplicates."""
    rows = (
        await db.execute(
            select(WebsiteSponsor)
            .where(WebsiteSponsor.tier == tier)
            .order_by(WebsiteSponsor.display_order, WebsiteSponsor.created_at, WebsiteSponsor.name)
        )
    ).scalars().all()
    for idx, s in enumerate(rows, start=1):
        if s.display_order != idx:
            s.display_order = idx


@router.get("/sponsors", response_model=list[SponsorOut])
async def list_website_sponsors(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_website_admin)
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
    current_user: User = Depends(require_website_admin),
):
    tier_sponsors = (
        await db.execute(
            select(WebsiteSponsor)
            .where(WebsiteSponsor.tier == body.tier)
            .order_by(WebsiteSponsor.display_order, WebsiteSponsor.created_at)
        )
    ).scalars().all()

    max_order = max([s.display_order for s in tier_sponsors], default=0)
    target_order = body.display_order

    if target_order <= 0 or target_order > max_order + 1:
        target_order = max_order + 1
    else:
        for s in tier_sponsors:
            if s.display_order >= target_order:
                s.display_order += 1

    data = body.model_dump()
    data["display_order"] = target_order
    row = WebsiteSponsor(**data)
    db.add(row)
    await db.flush()
    await _resequence_tier(db, body.tier)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/sponsors/{sponsor_id}", response_model=SponsorOut)
async def update_website_sponsor(
    sponsor_id: UUID,
    body: SponsorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = (await db.execute(select(WebsiteSponsor).where(WebsiteSponsor.id == sponsor_id))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Sponsor not found")

    old_tier = row.tier
    old_order = row.display_order
    update_data = body.model_dump(exclude_unset=True)
    new_tier = update_data.get("tier", old_tier)
    new_order = update_data.get("display_order")

    if new_order is not None and (new_order != old_order or new_tier != old_tier):
        tier_sponsors = (
            await db.execute(
                select(WebsiteSponsor)
                .where(WebsiteSponsor.tier == new_tier, WebsiteSponsor.id != sponsor_id)
                .order_by(WebsiteSponsor.display_order, WebsiteSponsor.created_at)
            )
        ).scalars().all()

        max_order = max([s.display_order for s in tier_sponsors], default=0)
        if new_order <= 0 or new_order > max_order + 1:
            target_order = max_order + 1
        else:
            target_order = new_order
            for s in tier_sponsors:
                if s.display_order >= target_order:
                    s.display_order += 1
        update_data["display_order"] = target_order

    for field, value in update_data.items():
        setattr(row, field, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await _resequence_tier(db, new_tier)
    if old_tier != new_tier:
        await _resequence_tier(db, old_tier)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/sponsors/{sponsor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_website_sponsor(
    sponsor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = (await db.execute(select(WebsiteSponsor).where(WebsiteSponsor.id == sponsor_id))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Sponsor not found")
    tier = row.tier
    await db.delete(row)
    await db.flush()
    await _resequence_tier(db, tier)
    await db.commit()
    return None
