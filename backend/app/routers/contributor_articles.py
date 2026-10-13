"""Contributor articles endpoints — any active portal user.

Interns, instructors, facilitators, and staff draft technical articles in
Markdown, edit their own drafts/revisions, and submit them into the
editorial queue. Admins bypass the ownership and status guards.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.models.website_article import WebsiteArticle
from app.schemas.website_article import (
    ArticleContributorOut,
    ArticleCreateIn,
    ArticleUpdateIn,
)
from app.services.articles.markdown import render_markdown_to_html, slugify

router = APIRouter(prefix="/articles", tags=["contributor-articles"])

# Statuses a non-admin author may still edit.
_EDITABLE_BY_AUTHOR = ("draft", "changes_requested", "archived")


def _is_admin(user: User) -> bool:
    return any(r in user.role_values for r in ("admin", "operations"))


def _author_initials(full_name: str) -> str | None:
    parts = [p for p in (full_name or "").split() if p and p[0].isalpha()]
    if not parts:
        return None
    return "".join(p[0] for p in parts[:2]).upper()


async def _unique_slug(db: AsyncSession, title: str) -> str:
    base = slugify(title)
    slug = base
    suffix = 2
    while (
        await db.execute(select(WebsiteArticle.id).where(WebsiteArticle.slug == slug))
    ).first() is not None:
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


async def _get_owned(article_id: UUID, user: User, db: AsyncSession) -> WebsiteArticle:
    row = (
        await db.execute(select(WebsiteArticle).where(WebsiteArticle.id == article_id))
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    if row.author_id != user.id and not _is_admin(user):
        raise HTTPException(status_code=403, detail="Not your article")
    return row


@router.get("/me", response_model=list[ArticleContributorOut])
async def list_my_articles(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WebsiteArticle)
    if not _is_admin(current_user):
        stmt = stmt.where(WebsiteArticle.author_id == current_user.id)
    rows = (
        await db.execute(
            stmt.order_by(WebsiteArticle.featured_order.asc(), WebsiteArticle.updated_at.desc())
        )
    ).scalars().all()
    return rows


@router.post("", response_model=ArticleContributorOut, status_code=status.HTTP_201_CREATED)
async def create_article(
    body: ArticleCreateIn,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    roles = current_user.role_values
    display_name = (body.author_display_name or "").strip() or current_user.full_name
    role = (body.author_role or "").strip() or (roles[0].title() if roles else None)
    initials = (body.author_initials or "").strip().upper() or _author_initials(display_name)
    row = WebsiteArticle(
        title=body.title.strip(),
        slug=await _unique_slug(db, body.title),
        summary=(body.summary or "").strip() or None,
        content_markdown=body.content_markdown,
        content_html=render_markdown_to_html(body.content_markdown),
        category=(body.category or "EDUCATION").strip().upper() or "EDUCATION",
        cover_image_url=(body.cover_image_url or "").strip() or None,
        status="draft",
        author_id=current_user.id,
        author_display_name=display_name,
        author_role=role,
        author_initials=initials,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/{article_id}", response_model=ArticleContributorOut)
async def update_article(
    article_id: UUID,
    body: ArticleUpdateIn,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_owned(article_id, current_user, db)
    if row.status not in _EDITABLE_BY_AUTHOR and not _is_admin(current_user):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit an article in '{row.status}' status",
        )
    data = body.model_dump(exclude_unset=True)
    if "title" in data and data["title"] is not None:
        row.title = data["title"].strip()
    if "summary" in data:
        row.summary = (data["summary"] or "").strip() or None
    if "content_markdown" in data and data["content_markdown"] is not None:
        row.content_markdown = data["content_markdown"]
        row.content_html = render_markdown_to_html(data["content_markdown"])
    if "category" in data and data["category"] is not None:
        row.category = data["category"].strip().upper() or row.category
    if "cover_image_url" in data:
        row.cover_image_url = (data["cover_image_url"] or "").strip() or None
    if "author_display_name" in data and data["author_display_name"]:
        row.author_display_name = data["author_display_name"].strip()
        if "author_initials" not in data:
            row.author_initials = _author_initials(row.author_display_name)
    if "author_role" in data:
        row.author_role = (data["author_role"] or "").strip() or None
    if "author_initials" in data and data["author_initials"] is not None:
        row.author_initials = data["author_initials"].strip().upper() or _author_initials(row.author_display_name)
    if "featured_order" in data and _is_admin(current_user):
        row.featured_order = data["featured_order"]
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


@router.post("/{article_id}/submit", response_model=ArticleContributorOut)
async def submit_article(
    article_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_owned(article_id, current_user, db)
    if row.status not in ("draft", "changes_requested"):
        raise HTTPException(
            status_code=400,
            detail=f"Only drafts or revisions can be submitted (current: '{row.status}')",
        )
    row.status = "submitted"
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row
