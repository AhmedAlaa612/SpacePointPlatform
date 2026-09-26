from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_active_user,
    require_article_author,
    require_cms_editor,
)
from app.db.session import get_db
from app.models.cms import Article, MediaClipping, Sponsor, StudentMission, WebsiteLead
from app.models.user import User
from app.schemas.cms import (
    ArticleAdminOut,
    ArticleCreate,
    ArticleReviewAction,
    ArticleUpdate,
    MediaClippingCreate,
    MediaClippingOut,
    MediaClippingUpdate,
    SponsorCreate,
    SponsorOut,
    SponsorUpdate,
    StudentMissionCreate,
    StudentMissionOut,
    StudentMissionUpdate,
    WebsiteLeadOut,
    WebsiteLeadStatusUpdate,
    compile_markdown_to_safe_html,
    slugify,
)

router = APIRouter(tags=["cms-admin"])


def _extract_initials(name: str) -> str:
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return "SP"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return f"{parts[0][0]}{parts[-1][0]}".upper()


async def _generate_unique_slug(db: AsyncSession, base_text: str, exclude_id: UUID | None = None) -> str:
    raw_slug = slugify(base_text)
    candidate = raw_slug
    counter = 1

    while True:
        stmt = select(Article.id).where(Article.slug == candidate)
        if exclude_id is not None:
            stmt = stmt.where(Article.id != exclude_id)
        existing = (await db.execute(stmt)).scalars().first()
        if not existing:
            return candidate
        counter += 1
        candidate = f"{raw_slug}-{counter}"


# ═══════════════════════════════════════════════════════════════════════════════
# CONTRIBUTOR AUTHORING PIPELINE (/cms/articles)
# Allowed roles: intern, instructor, facilitator, operations, admin
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/cms/articles/my", response_model=list[ArticleAdminOut])
async def list_my_articles(
    current_user: User = Depends(require_article_author),
    db: AsyncSession = Depends(get_db),
) -> list[Article]:
    """Returns articles authored by the currently authenticated user across all statuses."""
    stmt = (
        select(Article)
        .where(Article.author_id == current_user.id)
        .order_by(Article.updated_at.desc())
    )
    articles = (await db.execute(stmt)).scalars().all()
    return list(articles)


@router.post("/cms/articles", response_model=ArticleAdminOut, status_code=status.HTTP_201_CREATED)
async def create_article(
    payload: ArticleCreate,
    current_user: User = Depends(require_article_author),
    db: AsyncSession = Depends(get_db),
) -> Article:
    """Creates a new article draft or directly submits it for editorial review."""
    slug = await _generate_unique_slug(db, payload.slug or payload.title)
    html_content = compile_markdown_to_safe_html(payload.content_markdown)

    # Determine author metadata
    author_name = payload.author_display_name or current_user.full_name
    primary_role = (
        payload.author_role
        or (current_user.role_values[0].capitalize() if current_user.role_values else "Contributor")
    )
    initials = payload.author_initials or _extract_initials(author_name)

    initial_status = "in_review" if payload.submit_for_review else "draft"

    article = Article(
        slug=slug,
        title=payload.title.strip(),
        summary=payload.summary.strip() if payload.summary else None,
        category=payload.category.strip().upper(),
        cover_image_url=payload.cover_image_url,
        content_markdown=payload.content_markdown,
        content_html=html_content,
        author_id=current_user.id,
        author_display_name=author_name,
        author_role=primary_role,
        author_initials=initials,
        status=initial_status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(article)
    await db.commit()
    await db.refresh(article)
    return article


@router.get("/cms/articles/{article_id}", response_model=ArticleAdminOut)
async def get_article_detail(
    article_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Article:
    """Returns article details. Contributors can view their own articles; Ops/Admin can view any."""
    stmt = select(Article).where(Article.id == article_id)
    article = (await db.execute(stmt)).scalars().first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    is_author = article.author_id == current_user.id
    is_editor = any(r in current_user.role_values for r in ("admin", "operations"))

    if not is_author and not is_editor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return article


@router.patch("/cms/articles/{article_id}", response_model=ArticleAdminOut)
async def update_article(
    article_id: UUID,
    payload: ArticleUpdate,
    current_user: User = Depends(require_article_author),
    db: AsyncSession = Depends(get_db),
) -> Article:
    """Updates an article. If changes were requested, contributor can edit and resubmit to in_review."""
    stmt = select(Article).where(Article.id == article_id)
    article = (await db.execute(stmt)).scalars().first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    is_author = article.author_id == current_user.id
    is_editor = any(r in current_user.role_values for r in ("admin", "operations"))

    if not is_author and not is_editor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Guard: Published articles can only be edited by ops/admin
    if article.status == "published" and not is_editor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Published articles can only be edited by operations or administrators.",
        )

    if payload.title is not None:
        article.title = payload.title.strip()
        # Optionally regenerate slug if draft
        if article.status == "draft":
            article.slug = await _generate_unique_slug(db, payload.title, exclude_id=article.id)

    if payload.summary is not None:
        article.summary = payload.summary.strip() or None

    if payload.category is not None:
        article.category = payload.category.strip().upper()

    if payload.cover_image_url is not None:
        article.cover_image_url = payload.cover_image_url

    if payload.content_markdown is not None:
        article.content_markdown = payload.content_markdown
        article.content_html = compile_markdown_to_safe_html(payload.content_markdown)

    # Workflow submission transition
    if payload.submit_for_review is True:
        if article.status in ("draft", "changes_requested"):
            article.status = "in_review"

    article.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(article)
    return article


@router.delete("/cms/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(
    article_id: UUID,
    current_user: User = Depends(require_article_author),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deletes an article draft. Authors can only delete their own drafts; Ops/Admin can delete any non-published."""
    stmt = select(Article).where(Article.id == article_id)
    article = (await db.execute(stmt)).scalars().first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    is_author = article.author_id == current_user.id
    is_editor = any(r in current_user.role_values for r in ("admin", "operations"))

    if not is_author and not is_editor:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if is_author and not is_editor and article.status != "draft":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authors can only delete articles that are in draft status.",
        )

    await db.delete(article)
    await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# OPERATIONS & ADMIN WEBSITE SUITE (/operations/website)
# Allowed roles: operations, admin
# ═══════════════════════════════════════════════════════════════════════════════

# ── Editorial Review Queue ───────────────────────────────────────────────────

@router.get("/operations/website/articles", response_model=list[ArticleAdminOut])
async def list_all_articles(
    status_filter: str | None = Query(None, description="Filter by status: draft, in_review, changes_requested, published, archived"),
    category: str | None = Query(None, description="Filter by category"),
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> list[Article]:
    """Lists all articles across the platform for editorial review and management."""
    query = select(Article)
    if status_filter:
        query = query.where(Article.status == status_filter.lower())
    if category:
        query = query.where(func.upper(Article.category) == category.upper())

    query = query.order_by(Article.updated_at.desc())
    articles = (await db.execute(query)).scalars().all()
    return list(articles)


@router.post("/operations/website/articles/{article_id}/review", response_model=ArticleAdminOut)
async def review_article_action(
    article_id: UUID,
    action_in: ArticleReviewAction,
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> Article:
    """Editorial state machine action:

    - approve: Publishes article to the live website.
    - request_changes: Rejects draft back to author with required reviewer feedback notes.
    - unpublish: Reverts published article to draft.
    - archive: Retires article from public listings.
    """
    stmt = select(Article).where(Article.id == article_id)
    article = (await db.execute(stmt)).scalars().first()
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    action = action_in.action.lower()

    if action == "approve":
        article.status = "published"
        if not article.published_at:
            article.published_at = datetime.now(timezone.utc)
        article.reviewed_by_id = current_user.id
        article.reviewed_at = datetime.now(timezone.utc)
        if action_in.featured_order is not None:
            article.featured_order = action_in.featured_order

    elif action == "request_changes":
        if not action_in.reviewer_feedback or not action_in.reviewer_feedback.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Reviewer feedback is required when requesting changes.",
            )
        article.status = "changes_requested"
        article.reviewer_feedback = action_in.reviewer_feedback.strip()
        article.reviewed_by_id = current_user.id
        article.reviewed_at = datetime.now(timezone.utc)

    elif action == "unpublish":
        article.status = "draft"
        article.published_at = None

    elif action == "archive":
        article.status = "archived"

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid action '{action}'. Choose: approve, request_changes, unpublish, archive",
        )

    article.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(article)
    return article


# ── Sponsors CRUD ────────────────────────────────────────────────────────────

@router.get("/operations/website/sponsors", response_model=list[SponsorOut])
async def list_all_sponsors(
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> list[Sponsor]:
    query = select(Sponsor).order_by(Sponsor.display_order.asc(), Sponsor.created_at.asc())
    sponsors = (await db.execute(query)).scalars().all()
    return list(sponsors)


@router.post("/operations/website/sponsors", response_model=SponsorOut, status_code=status.HTTP_201_CREATED)
async def create_sponsor(
    payload: SponsorCreate,
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> Sponsor:
    sponsor = Sponsor(
        name=payload.name.strip(),
        logo_url=payload.logo_url.strip(),
        website_url=payload.website_url.strip() if payload.website_url else None,
        tier=payload.tier.strip().lower(),
        display_order=payload.display_order,
        is_active=payload.is_active,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(sponsor)
    await db.commit()
    await db.refresh(sponsor)
    return sponsor


@router.patch("/operations/website/sponsors/{sponsor_id}", response_model=SponsorOut)
async def update_sponsor(
    sponsor_id: UUID,
    payload: SponsorUpdate,
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> Sponsor:
    stmt = select(Sponsor).where(Sponsor.id == sponsor_id)
    sponsor = (await db.execute(stmt)).scalars().first()
    if not sponsor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sponsor not found")

    if payload.name is not None:
        sponsor.name = payload.name.strip()
    if payload.logo_url is not None:
        sponsor.logo_url = payload.logo_url.strip()
    if payload.website_url is not None:
        sponsor.website_url = payload.website_url.strip() or None
    if payload.tier is not None:
        sponsor.tier = payload.tier.strip().lower()
    if payload.display_order is not None:
        sponsor.display_order = payload.display_order
    if payload.is_active is not None:
        sponsor.is_active = payload.is_active

    sponsor.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(sponsor)
    return sponsor


@router.delete("/operations/website/sponsors/{sponsor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sponsor(
    sponsor_id: UUID,
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> None:
    stmt = select(Sponsor).where(Sponsor.id == sponsor_id)
    sponsor = (await db.execute(stmt)).scalars().first()
    if not sponsor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sponsor not found")
    await db.delete(sponsor)
    await db.commit()


# ── Media Clippings CRUD ─────────────────────────────────────────────────────

@router.get("/operations/website/media", response_model=list[MediaClippingOut])
async def list_all_media(
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> list[MediaClipping]:
    query = select(MediaClipping).order_by(MediaClipping.published_date.desc())
    clippings = (await db.execute(query)).scalars().all()
    return list(clippings)


@router.post("/operations/website/media", response_model=MediaClippingOut, status_code=status.HTTP_201_CREATED)
async def create_media_clipping(
    payload: MediaClippingCreate,
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> MediaClipping:
    clipping = MediaClipping(
        publisher_name=payload.publisher_name.strip(),
        article_title=payload.article_title.strip(),
        article_url=payload.article_url.strip(),
        published_date=payload.published_date,
        logo_url=payload.logo_url.strip() if payload.logo_url else None,
        is_arabic=payload.is_arabic,
        snippet=payload.snippet.strip() if payload.snippet else None,
        display_order=payload.display_order,
        is_active=payload.is_active,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(clipping)
    await db.commit()
    await db.refresh(clipping)
    return clipping


@router.patch("/operations/website/media/{clipping_id}", response_model=MediaClippingOut)
async def update_media_clipping(
    clipping_id: UUID,
    payload: MediaClippingUpdate,
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> MediaClipping:
    stmt = select(MediaClipping).where(MediaClipping.id == clipping_id)
    clipping = (await db.execute(stmt)).scalars().first()
    if not clipping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media clipping not found")

    if payload.publisher_name is not None:
        clipping.publisher_name = payload.publisher_name.strip()
    if payload.article_title is not None:
        clipping.article_title = payload.article_title.strip()
    if payload.article_url is not None:
        clipping.article_url = payload.article_url.strip()
    if payload.published_date is not None:
        clipping.published_date = payload.published_date
    if payload.logo_url is not None:
        clipping.logo_url = payload.logo_url.strip() or None
    if payload.is_arabic is not None:
        clipping.is_arabic = payload.is_arabic
    if payload.snippet is not None:
        clipping.snippet = payload.snippet.strip() or None
    if payload.display_order is not None:
        clipping.display_order = payload.display_order
    if payload.is_active is not None:
        clipping.is_active = payload.is_active

    clipping.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(clipping)
    return clipping


@router.delete("/operations/website/media/{clipping_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media_clipping(
    clipping_id: UUID,
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> None:
    stmt = select(MediaClipping).where(MediaClipping.id == clipping_id)
    clipping = (await db.execute(stmt)).scalars().first()
    if not clipping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media clipping not found")
    await db.delete(clipping)
    await db.commit()


# ── Student Missions CRUD ────────────────────────────────────────────────────

@router.get("/operations/website/student-missions", response_model=list[StudentMissionOut])
async def list_all_student_missions(
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> list[StudentMission]:
    query = select(StudentMission).order_by(StudentMission.display_order.asc(), StudentMission.created_at.asc())
    missions = (await db.execute(query)).scalars().all()
    return list(missions)


@router.post("/operations/website/student-missions", response_model=StudentMissionOut, status_code=status.HTTP_201_CREATED)
async def create_student_mission(
    payload: StudentMissionCreate,
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> StudentMission:
    mission = StudentMission(
        student_name=payload.student_name.strip(),
        project_title=payload.project_title.strip(),
        category=payload.category.strip(),
        description=payload.description.strip(),
        docx_url=payload.docx_url.strip() if payload.docx_url else None,
        photo_url=payload.photo_url.strip() if payload.photo_url else None,
        metrics_json=payload.metrics_json or {},
        display_order=payload.display_order,
        is_active=payload.is_active,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(mission)
    await db.commit()
    await db.refresh(mission)
    return mission


@router.patch("/operations/website/student-missions/{mission_id}", response_model=StudentMissionOut)
async def update_student_mission(
    mission_id: UUID,
    payload: StudentMissionUpdate,
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> StudentMission:
    stmt = select(StudentMission).where(StudentMission.id == mission_id)
    mission = (await db.execute(stmt)).scalars().first()
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student mission not found")

    if payload.student_name is not None:
        mission.student_name = payload.student_name.strip()
    if payload.project_title is not None:
        mission.project_title = payload.project_title.strip()
    if payload.category is not None:
        mission.category = payload.category.strip()
    if payload.description is not None:
        mission.description = payload.description.strip()
    if payload.docx_url is not None:
        mission.docx_url = payload.docx_url.strip() or None
    if payload.photo_url is not None:
        mission.photo_url = payload.photo_url.strip() or None
    if payload.metrics_json is not None:
        mission.metrics_json = payload.metrics_json
    if payload.display_order is not None:
        mission.display_order = payload.display_order
    if payload.is_active is not None:
        mission.is_active = payload.is_active

    mission.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(mission)
    return mission


@router.delete("/operations/website/student-missions/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student_mission(
    mission_id: UUID,
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> None:
    stmt = select(StudentMission).where(StudentMission.id == mission_id)
    mission = (await db.execute(stmt)).scalars().first()
    if not mission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student mission not found")
    await db.delete(mission)
    await db.commit()


# ── Website Leads CRM Management ─────────────────────────────────────────────

@router.get("/operations/website/leads", response_model=list[WebsiteLeadOut])
async def list_website_leads(
    lead_type: str | None = Query(None, description="Filter by type: workshop_booking, newsletter, inquiry"),
    status_filter: str | None = Query(None, description="Filter by status: new, contacted, converted, archived"),
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> list[WebsiteLead]:
    query = select(WebsiteLead)
    if lead_type:
        query = query.where(WebsiteLead.lead_type == lead_type.lower())
    if status_filter:
        query = query.where(WebsiteLead.status == status_filter.lower())

    query = query.order_by(WebsiteLead.created_at.desc())
    leads = (await db.execute(query)).scalars().all()
    return list(leads)


@router.patch("/operations/website/leads/{lead_id}", response_model=WebsiteLeadOut)
async def update_lead_status(
    lead_id: UUID,
    payload: WebsiteLeadStatusUpdate,
    current_user: User = Depends(require_cms_editor),
    db: AsyncSession = Depends(get_db),
) -> WebsiteLead:
    stmt = select(WebsiteLead).where(WebsiteLead.id == lead_id)
    lead = (await db.execute(stmt)).scalars().first()
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    valid_statuses = {"new", "contacted", "converted", "archived"}
    if payload.status.lower() not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}",
        )

    lead.status = payload.status.lower()
    lead.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(lead)
    return lead
