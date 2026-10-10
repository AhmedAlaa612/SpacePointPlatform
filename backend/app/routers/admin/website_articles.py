from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.user import User
from app.models.website_article import WebsiteArticle
from app.schemas.website_article import ArticleContributorOut, ArticleReviewIn

router = APIRouter(prefix="/website", tags=["admin-website-articles"])


@router.get("/articles", response_model=list[ArticleContributorOut])
async def list_website_articles(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    """Every article across all statuses (editorial queue view)."""
    rows = (
        await db.execute(select(WebsiteArticle).order_by(WebsiteArticle.updated_at.desc()))
    ).scalars().all()
    return rows


@router.post("/articles/{article_id}/review", response_model=ArticleContributorOut)
async def review_website_article(
    article_id: UUID,
    body: ArticleReviewIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    row = (
        await db.execute(select(WebsiteArticle).where(WebsiteArticle.id == article_id))
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")

    if body.action == "approve":
        row.status = "published"
        row.published_at = datetime.now(timezone.utc)
        row.reviewer_id = current_user.id
        row.reviewer_feedback = None
    elif body.action == "request_changes":
        if not (body.feedback or "").strip():
            raise HTTPException(status_code=400, detail="Feedback is required to request changes")
        row.status = "changes_requested"
        row.reviewer_id = current_user.id
        row.reviewer_feedback = body.feedback.strip()
    elif body.action == "unpublish":
        row.status = "draft"
        row.published_at = None
        row.reviewer_id = current_user.id
        row.reviewer_feedback = None
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/articles/{article_id}/unpublish", response_model=ArticleContributorOut)
async def unpublish_website_article(
    article_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    row = (
        await db.execute(select(WebsiteArticle).where(WebsiteArticle.id == article_id))
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    row.status = "draft"
    row.published_at = None
    row.reviewer_id = current_user.id
    row.reviewer_feedback = None
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_website_article(
    article_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    row = (
        await db.execute(select(WebsiteArticle).where(WebsiteArticle.id == article_id))
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    await db.delete(row)
    await db.commit()
    return None
