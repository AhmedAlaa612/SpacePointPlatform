from datetime import datetime, timezone
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_website_admin
from app.db.session import get_db
from app.models.sessions.program import Program
from app.models.user import User
from app.models.website_case_study import WebsiteCaseStudy
from app.models.website_case_studies_header import WebsiteCaseStudiesHeader
from app.schemas.website_case_study import (
    CaseStudySnapshotOut,
    CaseStudySnapshotRequest,
    CreateCaseStudyFromProgramIn,
    ResetFieldIn,
    WebsiteCaseStudyCreate,
    WebsiteCaseStudyOut,
    WebsiteCaseStudyUpdate,
)
from app.schemas.website_case_studies_header import (
    WebsiteCaseStudiesHeaderOut,
    WebsiteCaseStudiesHeaderUpdate,
)
from app.services.articles.markdown import slugify
from app.services.program_web_live import (
    CASE_STUDY_LIVE_FIELDS,
    apply_case_study_live_merge,
    invalidate_program_web_cache,
    resolve_case_study_live,
)
from app.services.program_web_pages import create_case_study_from_program
from app.services.website_case_studies import (
    get_or_seed_case_studies_header,
    pull_case_study_snapshot,
    unique_case_study_slug,
)

router = APIRouter(prefix="/website", tags=["admin-website-case-studies"])


async def _serialize_admin_cs(
    db: AsyncSession,
    row: WebsiteCaseStudy,
    *,
    include_admin_meta: bool = False,
) -> dict:
    d = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    if not row.live_linked:
        if include_admin_meta:
            d["field_states"] = {}
        return d
    live = await resolve_case_study_live(
        db,
        source_type=row.source_type,
        program_id=row.program_id,
        cohort_id=row.cohort_id,
        cohort_ids=row.cohort_ids,
        use_cache=False,
    )
    return apply_case_study_live_merge(
        d,
        live=live,
        live_linked=True,
        overrides=row.overrides,
        hidden_sections=row.hidden_sections,
        include_admin_meta=include_admin_meta,
    )


@router.get("/case-studies-header", response_model=WebsiteCaseStudiesHeaderOut)
async def get_case_studies_header(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    return await get_or_seed_case_studies_header(db)


@router.put("/case-studies-header", response_model=WebsiteCaseStudiesHeaderOut)
async def update_case_studies_header(
    body: WebsiteCaseStudiesHeaderUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    row = await get_or_seed_case_studies_header(db)
    row.stats = [s.model_dump() for s in body.stats]
    row.partners = [p.model_dump() for p in body.partners]
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return row


@router.get("/case-studies", response_model=list[WebsiteCaseStudyOut])
async def list_case_studies(
    program_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    stmt = select(WebsiteCaseStudy)
    if program_id is not None:
        stmt = stmt.where(WebsiteCaseStudy.program_id == program_id)
    rows = (
        await db.execute(
            stmt.order_by(
                WebsiteCaseStudy.display_order.asc(),
                WebsiteCaseStudy.created_at.desc(),
            )
        )
    ).scalars().all()
    return [await _serialize_admin_cs(db, r, include_admin_meta=False) for r in rows]


@router.get("/case-studies/{case_study_id}", response_model=WebsiteCaseStudyOut)
async def get_case_study(
    case_study_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    row = (
        await db.execute(select(WebsiteCaseStudy).where(WebsiteCaseStudy.id == case_study_id))
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Case study not found")
    return await _serialize_admin_cs(db, row, include_admin_meta=True)


@router.post("/case-studies/from-program", response_model=WebsiteCaseStudyOut, status_code=status.HTTP_201_CREATED)
async def create_case_study_from_program_route(
    body: CreateCaseStudyFromProgramIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    """Create a hybrid-live draft Case Study from a Program + ordered list of Cohorts."""
    program = await db.get(Program, body.program_id)
    if not program:
        raise HTTPException(status_code=404, detail="Program not found")
    cs = await create_case_study_from_program(
        db,
        program=program,
        cohort_ids=body.cohort_ids,
        title=body.title,
        include_buckets=body.include_buckets,
    )
    return await _serialize_admin_cs(db, cs, include_admin_meta=True)


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

    if not data.get("preview_token"):
        data["preview_token"] = secrets.token_urlsafe(24)

    row = WebsiteCaseStudy(**data)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return await _serialize_admin_cs(db, row, include_admin_meta=True)


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

    # Merge explicit overrides dict if provided; otherwise track live-field edits when live_linked
    existing_overrides = dict(row.overrides or {})
    if "overrides" in data and isinstance(data["overrides"], dict):
        existing_overrides = dict(data["overrides"])
        data.pop("overrides")
    elif row.live_linked:
        for lf in CASE_STUDY_LIVE_FIELDS:
            if lf in data:
                existing_overrides[lf] = data[lf]
    row.overrides = existing_overrides

    for field, value in data.items():
        if field != "preview_token":
            setattr(row, field, value)

    if not row.preview_token:
        row.preview_token = secrets.token_urlsafe(24)

    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    invalidate_program_web_cache(row.program_id)
    return await _serialize_admin_cs(db, row, include_admin_meta=True)


@router.post("/case-studies/{case_study_id}/reset-field", response_model=WebsiteCaseStudyOut)
async def reset_case_study_field(
    case_study_id: UUID,
    body: ResetFieldIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    row = (
        await db.execute(select(WebsiteCaseStudy).where(WebsiteCaseStudy.id == case_study_id))
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Case study not found")
    ov = dict(row.overrides or {})
    ov.pop(body.field, None)
    row.overrides = ov
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    invalidate_program_web_cache(row.program_id)
    return await _serialize_admin_cs(db, row, include_admin_meta=True)


@router.post("/case-studies/{case_study_id}/publish", response_model=WebsiteCaseStudyOut)
async def publish_case_study(
    case_study_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    row = (
        await db.execute(select(WebsiteCaseStudy).where(WebsiteCaseStudy.id == case_study_id))
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Case study not found")
    row.is_published = True
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    invalidate_program_web_cache(row.program_id)
    return await _serialize_admin_cs(db, row, include_admin_meta=True)


@router.post("/case-studies/{case_study_id}/unpublish", response_model=WebsiteCaseStudyOut)
async def unpublish_case_study(
    case_study_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    row = (
        await db.execute(select(WebsiteCaseStudy).where(WebsiteCaseStudy.id == case_study_id))
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Case study not found")
    row.is_published = False
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    invalidate_program_web_cache(row.program_id)
    return await _serialize_admin_cs(db, row, include_admin_meta=True)


@router.post("/case-studies/{case_study_id}/preview-token/regenerate", response_model=WebsiteCaseStudyOut)
async def regenerate_case_study_preview_token(
    case_study_id: UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_website_admin),
):
    row = (
        await db.execute(select(WebsiteCaseStudy).where(WebsiteCaseStudy.id == case_study_id))
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Case study not found")
    row.preview_token = secrets.token_urlsafe(24)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return await _serialize_admin_cs(db, row, include_admin_meta=True)


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
