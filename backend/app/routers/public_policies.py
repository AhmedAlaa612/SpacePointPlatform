from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.website_policy import WebsitePolicy
from app.schemas.website_policy import WebsitePolicyOut, WebsitePolicySummaryOut
from app.services.website_policies import seed_default_policies

router = APIRouter(prefix="/public/website/policies", tags=["public-website-policies"])

# Known aliases for convenience
_SLUG_ALIASES = {
    "privacy": "privacy-policy",
    "terms": "terms-of-service",
    "esg": "impact",
    "esg-strategy": "impact",
}


@router.get("", response_model=list[WebsitePolicySummaryOut])
async def list_public_policies(db: AsyncSession = Depends(get_db)):
    """List all active policies for the marketing website footer and policy directory."""
    # Ensure default seeds are present
    await seed_default_policies(db)
    stmt = (
        select(WebsitePolicy)
        .where(WebsitePolicy.is_active.is_(True))
        .order_by(WebsitePolicy.display_order.asc(), WebsitePolicy.created_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return rows


@router.get("/{slug}", response_model=WebsitePolicyOut)
async def get_public_policy_by_slug(slug: str, db: AsyncSession = Depends(get_db)):
    """Fetch an active policy by its URL slug (with alias resolution)."""
    await seed_default_policies(db)
    clean = (slug or "").strip().lower()
    canonical_slug = _SLUG_ALIASES.get(clean, clean)

    stmt = select(WebsitePolicy).where(
        WebsitePolicy.is_active.is_(True),
        or_(
            WebsitePolicy.slug == clean,
            WebsitePolicy.slug == canonical_slug,
        ),
    )
    row = (await db.execute(stmt)).scalars().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Policy not found")
    return row
