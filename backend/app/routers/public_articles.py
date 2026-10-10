"""Public articles endpoints — no auth required.

Serve what spacepoint.ae/insights consumes: the published list
(optional ?category=...&limit=...) and the single-article slug view.
Only `published` rows are ever visible here.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.website_article import WebsiteArticle
from app.schemas.website_article import ArticlePublicOut

router = APIRouter(prefix="/public", tags=["public-articles"])


@router.get("/articles", response_model=list[ArticlePublicOut])
async def list_public_articles(
    category: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WebsiteArticle).where(WebsiteArticle.status == "published")
    if category and category != "ALL":
        stmt = stmt.where(WebsiteArticle.category == category)
    stmt = stmt.order_by(
        WebsiteArticle.featured_order.asc(),
        WebsiteArticle.published_at.desc().nullslast(),
        WebsiteArticle.created_at.desc(),
    ).limit(limit)
    try:
        rows = (await db.execute(stmt)).scalars().all()
    except Exception:
        return []
    return rows


@router.get("/articles/{slug}", response_model=ArticlePublicOut)
async def get_public_article(slug: str, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            select(WebsiteArticle).where(
                WebsiteArticle.slug == slug,
                WebsiteArticle.status == "published",
            )
        )
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return row
