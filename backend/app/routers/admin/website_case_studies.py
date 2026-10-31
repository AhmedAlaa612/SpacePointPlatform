from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_website_admin
from app.db.session import get_db
from app.models.user import User
from app.models.website_case_study import WebsiteCaseStudy
from app.models.website_case_studies_header import WebsiteCaseStudiesHeader
from app.schemas.website_case_study import (
    CaseStudySnapshotOut,
    CaseStudySnapshotRequest,
    WebsiteCaseStudyCreate,
    WebsiteCaseStudyOut,
    WebsiteCaseStudyUpdate,
)
from app.schemas.website_case_studies_header import (
    WebsiteCaseStudiesHeaderOut,
    WebsiteCaseStudiesHeaderUpdate,
)
from app.services.articles.markdown import slugify
from app.services.website_case_studies import pull_case_study_snapshot, unique_case_study_slug

router = APIRouter(prefix="/website", tags=["admin-website-case-studies"])


@router.get("/case-studies-header", response_model=WebsiteCaseStudiesHeaderOut)
async def get_case_studies_header(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    row = (await db.execute(select(WebsiteCaseStudiesHeader).where(WebsiteCaseStudiesHeader.id == 1))).scalar_one_or_none()
    if not row:
        row = WebsiteCaseStudiesHeader(id=1, stats=[], partners=[])
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row


@router.put("/case-studies-header", response_model=WebsiteCaseStudiesHeaderOut)
async def update_case_studies_header(
    body: WebsiteCaseStudiesHeaderUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    row = (await db.execute(select(WebsiteCaseStudiesHeader).where(WebsiteCaseStudiesHeader.id == 1))).scalar_one_or_none()
    if not row:
        row = WebsiteCaseStudiesHeader(id=1)
        db.add(row)
    row.stats = [s.model_dump() for s in body.stats]
    row.partners = [p.model_dump() for p in body.partners]
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/case-studies", response_model=list[WebsiteCaseStudyOut])
async def list_case_studies(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    rows = (
        await db.execute(
            select(WebsiteCaseStudy).order_by(
                WebsiteCaseStudy.display_order.asc(),
                WebsiteCaseStudy.created_at.desc(),
            )
        )
    ).scalars().all()
    return rows


@router.post("/case-studies/pull-snapshot", response_model=CaseStudySnapshotOut)
async def pull_snapshot(
    body: CaseStudySnapshotRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    """Aggregate metrics and template data from cohorts/programs for ops preview and pre-fill."""
    return await pull_case_study_snapshot(db, body)


@router.post("/case-studies", response_model=WebsiteCaseStudyOut, status_code=status.HTTP_201_CREATED)
async def create_case_study(
    body: WebsiteCaseStudyCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    data = body.model_dump()
    slug_val = (data.get("slug") or "").strip()
    data["slug"] = slug_val if slug_val else await unique_case_study_slug(db, data["title"])

    # If this is marked featured, unfeature others to keep a single primary
    if data.get("is_featured"):
        featured_rows = (
            await db.execute(select(WebsiteCaseStudy).where(WebsiteCaseStudy.is_featured.is_(True)))
        ).scalars().all()
        for r in featured_rows:
            r.is_featured = False

    # Convert pydantic models in lists to dicts if needed
    for json_key in [
        "cohort_ids", "partners", "metrics", "card_metrics", "gallery_images",
        "highlights", "curriculum_chapters", "structure_sections", "visibility_stats",
        "spotlights", "testimonials",
    ]:
        if json_key in data and isinstance(data[json_key], list):
            data[json_key] = [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in data[json_key]
            ]

    if "cohort_ids" in data and isinstance(data["cohort_ids"], list):
        data["cohort_ids"] = [str(x) for x in data["cohort_ids"]]

    row = WebsiteCaseStudy(**data)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.put("/case-studies/{case_study_id}", response_model=WebsiteCaseStudyOut)
async def update_case_study(
    case_study_id: UUID,
    body: WebsiteCaseStudyUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    row = (
        await db.execute(select(WebsiteCaseStudy).where(WebsiteCaseStudy.id == case_study_id))
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Case study not found")

    data = body.model_dump(exclude_unset=True)
    if "slug" in data and data["slug"]:
        clean_slug = slugify(data["slug"])
        existing = (
            await db.execute(
                select(WebsiteCaseStudy).where(
                    WebsiteCaseStudy.slug == clean_slug,
                    WebsiteCaseStudy.id != case_study_id,
                )
            )
        ).scalars().first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Slug '{clean_slug}' is already in use by another case study")
        data["slug"] = clean_slug

    if "cohort_ids" in data and isinstance(data["cohort_ids"], list):
        data["cohort_ids"] = [str(x) for x in data["cohort_ids"]]

    if data.get("is_featured"):
        featured_rows = (
            await db.execute(
                select(WebsiteCaseStudy).where(
                    WebsiteCaseStudy.is_featured.is_(True),
                    WebsiteCaseStudy.id != case_study_id,
                )
            )
        ).scalars().all()
        for r in featured_rows:
            r.is_featured = False

    for json_key in [
        "cohort_ids", "partners", "metrics", "card_metrics", "gallery_images",
        "highlights", "curriculum_chapters", "structure_sections", "visibility_stats",
        "spotlights", "testimonials",
    ]:
        if json_key in data and isinstance(data[json_key], list):
            data[json_key] = [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in data[json_key]
            ]

    for field, value in data.items():
        setattr(row, field, value)

    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/case-studies/{case_study_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_case_study(
    case_study_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    row = (
        await db.execute(select(WebsiteCaseStudy).where(WebsiteCaseStudy.id == case_study_id))
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Case study not found")

    await db.delete(row)
    await db.commit()
    return None
