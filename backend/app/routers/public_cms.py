from datetime import datetime, timezone
import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.cms import Article, MediaClipping, Sponsor, StudentMission, WebsiteLead
from app.schemas.cms import (
    ArticlePublicOut,
    MediaClippingOut,
    SponsorOut,
    StudentMissionOut,
    WebsiteLeadCreate,
)

router = APIRouter(prefix="/public", tags=["public-website"])


# ── Articles ─────────────────────────────────────────────────────────────────

@router.get("/articles")
async def list_public_articles(
    category: str | None = Query(None, description="Filter by category (TECHNOLOGY, EDUCATION, SCIENCE, STUDENT_STORIES)"),
    search: str | None = Query(None, description="Search keyword in title, summary, or author"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(12, ge=1, le=50, description="Items per page"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Returns paginated, published articles for the Astro marketing website."""
    query = select(Article).where(Article.status == "published")

    if category and category.upper() != "ALL":
        query = query.where(func.upper(Article.category) == category.upper())

    if search:
        search_filter = f"%{search.strip()}%"
        query = query.where(
            or_(
                Article.title.ilike(search_filter),
                Article.summary.ilike(search_filter),
                Article.author_display_name.ilike(search_filter),
            )
        )

    # Count total matching rows
    count_query = select(func.count()).select_from(query.subquery())
    total_count = (await db.execute(count_query)).scalar() or 0

    # Sort: sticky/featured first, then newest published
    offset = (page - 1) * limit
    paged_query = (
        query.order_by(
            Article.featured_order.asc().nullslast(),
            Article.published_at.desc().nullslast(),
            Article.created_at.desc(),
        )
        .offset(offset)
        .limit(limit)
    )

    rows = (await db.execute(paged_query)).scalars().all()

    return {
        "items": [ArticlePublicOut.model_validate(r) for r in rows],
        "total": total_count,
        "page": page,
        "limit": limit,
        "total_pages": math.ceil(total_count / limit) if total_count > 0 else 1,
    }


@router.get("/articles/{slug}")
async def get_public_article(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Returns a single published article and previous/next article navigation."""
    stmt = select(Article).where(Article.slug == slug, Article.status == "published")
    article = (await db.execute(stmt)).scalars().first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    # Fetch next and previous articles for navigation
    prev_stmt = (
        select(Article.slug, Article.title)
        .where(
            Article.status == "published",
            Article.published_at < (article.published_at or article.created_at),
        )
        .order_by(Article.published_at.desc())
        .limit(1)
    )
    next_stmt = (
        select(Article.slug, Article.title)
        .where(
            Article.status == "published",
            Article.published_at > (article.published_at or article.created_at),
        )
        .order_by(Article.published_at.asc())
        .limit(1)
    )

    prev_row = (await db.execute(prev_stmt)).first()
    next_row = (await db.execute(next_stmt)).first()

    return {
        "article": ArticlePublicOut.model_validate(article),
        "prev_article": {"slug": prev_row[0], "title": prev_row[1]} if prev_row else None,
        "next_article": {"slug": next_row[0], "title": next_row[1]} if next_row else None,
    }


# ── Sponsors ─────────────────────────────────────────────────────────────────

@router.get("/sponsors")
async def list_public_sponsors(
    tier: str | None = Query(None, description="Optional tier filter: client, partner, supporter, academic"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Returns active sponsors grouped by tier and sorted by display_order for the homepage marquee."""
    query = select(Sponsor).where(Sponsor.is_active.is_(True))
    if tier:
        query = query.where(func.lower(Sponsor.tier) == tier.lower())

    query = query.order_by(Sponsor.display_order.asc(), Sponsor.created_at.asc())
    sponsors = (await db.execute(query)).scalars().all()

    grouped: dict[str, list[dict]] = {
        "client": [],
        "partner": [],
        "supporter": [],
        "academic": [],
    }

    all_sponsors = []
    for s in sponsors:
        s_data = SponsorOut.model_validate(s).model_dump()
        all_sponsors.append(s_data)
        tier_key = (s.tier or "partner").lower()
        if tier_key in grouped:
            grouped[tier_key].append(s_data)
        else:
            grouped.setdefault(tier_key, []).append(s_data)

    return {
        "all": all_sponsors,
        "grouped": grouped,
    }


# ── Media Coverage ───────────────────────────────────────────────────────────

@router.get("/media")
async def list_public_media(
    db: AsyncSession = Depends(get_db),
) -> list[MediaClippingOut]:
    """Returns press and media clippings ordered by publication date descending."""
    query = (
        select(MediaClipping)
        .where(MediaClipping.is_active.is_(True))
        .order_by(MediaClipping.published_date.desc(), MediaClipping.display_order.asc())
    )
    clippings = (await db.execute(query)).scalars().all()
    return [MediaClippingOut.model_validate(c) for c in clippings]


# ── Student Missions ─────────────────────────────────────────────────────────

@router.get("/student-missions")
async def list_public_student_missions(
    category: str | None = Query(None, description="Filter by mission category"),
    db: AsyncSession = Depends(get_db),
) -> list[StudentMissionOut]:
    """Returns active showcase student projects with download report links."""
    query = select(StudentMission).where(StudentMission.is_active.is_(True))
    if category:
        query = query.where(StudentMission.category.ilike(f"%{category}%"))

    query = query.order_by(StudentMission.display_order.asc(), StudentMission.created_at.asc())
    missions = (await db.execute(query)).scalars().all()
    return [StudentMissionOut.model_validate(m) for m in missions]


# ── Leads (Workshops, Newsletter, Inquiries) ─────────────────────────────────

@router.post("/leads", status_code=status.HTTP_201_CREATED)
async def create_public_lead(
    payload: WebsiteLeadCreate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Receives website lead submissions (workshop bookings, newsletter, general inquiry).

    Replaces legacy Google Form redirects with an integrated CRM pipeline.
    """
    valid_lead_types = {"workshop_booking", "newsletter", "inquiry"}
    if payload.lead_type not in valid_lead_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid lead_type. Must be one of: {', '.join(valid_lead_types)}",
        )

    # Clean and insert lead record
    new_lead = WebsiteLead(
        lead_type=payload.lead_type,
        contact_name=payload.contact_name.strip() if payload.contact_name else None,
        email=str(payload.email).strip().lower(),
        phone=payload.phone.strip() if payload.phone else None,
        organization_name=payload.organization_name.strip() if payload.organization_name else None,
        program_interest=payload.program_interest.strip() if payload.program_interest else None,
        details=payload.details or {},
        status="new",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(new_lead)
    await db.commit()
    await db.refresh(new_lead)

    return {
        "success": True,
        "lead_id": str(new_lead.id),
        "message": (
            "Thank you for subscribing to our newsletter!"
            if payload.lead_type == "newsletter"
            else "Thank you for reaching out! A SpacePoint mission coordinator will contact you shortly."
        ),
    }
