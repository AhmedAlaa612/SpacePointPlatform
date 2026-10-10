"""Public sponsors endpoint — no auth required.

Lives at GET /public/sponsors (not /public/website/*): the marketing
site's getSponsors() already calls this path, so it predates the
Step 1–2 namespace. Returns active sponsors ordered by display_order,
grouped by tier by default (the shape the site consumes) or as a flat
list with ?grouped=false.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.website_sponsor import WebsiteSponsor
from app.schemas.website_sponsor import SponsorOut, SponsorsGroupedOut

router = APIRouter(prefix="/public", tags=["public-sponsors"])

_GROUP_KEYS = {
    "client": "clients",
    "partner": "partners",
    "supporter": "supporters",
    "academic": "academic",
    "industry_leader": "industry_leaders",
}


@router.get("/sponsors")
async def list_public_sponsors(
    grouped: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
):
    """Active sponsors ordered by display_order. Grouped by tier by
    default ({clients, partners, supporters, academic, industry_leaders});
    ?grouped=false returns the flat ordered list instead. Unseeded (fresh
    table, migration not yet run) reads as empty rather than a 500 so the
    marketing site's fallback content stays in charge."""
    try:
        rows = (
            await db.execute(
                select(WebsiteSponsor)
                .where(WebsiteSponsor.is_active.is_(True))
                .order_by(WebsiteSponsor.display_order, WebsiteSponsor.name)
            )
        ).scalars().all()
    except Exception:
        return SponsorsGroupedOut() if grouped else []
    items = [SponsorOut.model_validate(r).model_dump(mode="json") for r in rows]
    if not grouped:
        return items
    grouped_out: dict[str, list] = {key: [] for key in _GROUP_KEYS.values()}
    for item in items:
        key = _GROUP_KEYS.get(item["tier"])
        if key is not None:
            grouped_out[key].append(item)
    return grouped_out
