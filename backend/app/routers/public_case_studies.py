"""Public website Case Studies endpoint — no auth required.

The marketing site (spacepoint-website) reads its case studies and missions here
so ops updates and newly added case studies reflect immediately.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.website_case_study import WebsiteCaseStudy
from app.models.website_case_studies_header import WebsiteCaseStudiesHeader
from app.schemas.website_case_study import WebsiteCaseStudyOut
from app.schemas.website_case_studies_header import WebsiteCaseStudiesHeaderOut
from app.services.program_web_live import apply_case_study_live_merge, resolve_case_study_live
from app.services.website_case_studies import default_case_studies_header_payload

router = APIRouter(prefix="/public/website", tags=["public-case-studies"])


async def _serialize_public_cs(db: AsyncSession, row: WebsiteCaseStudy) -> dict:
    d = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    if not row.live_linked:
        return d
    live = await resolve_case_study_live(
        db,
        source_type=row.source_type,
        program_id=row.program_id,
        cohort_id=row.cohort_id,
        cohort_ids=row.cohort_ids,
        use_cache=True,
        cache_id=str(row.id),
    )
    return apply_case_study_live_merge(
        d,
        live=live,
        live_linked=True,
        overrides=row.overrides,
        hidden_sections=row.hidden_sections,
        include_admin_meta=False,
    )


@router.get("/case-studies-header", response_model=WebsiteCaseStudiesHeaderOut)
async def get_public_case_studies_header(db: AsyncSession = Depends(get_db)):
    """Fetch the case studies page header stats and trusted partners."""
    try:
        row = (await db.execute(select(WebsiteCaseStudiesHeader).where(WebsiteCaseStudiesHeader.id == 1))).scalar_one_or_none()
        if not row:
            return WebsiteCaseStudiesHeaderOut(**default_case_studies_header_payload())
        return row
    except Exception:
        return WebsiteCaseStudiesHeaderOut(**default_case_studies_header_payload())


@router.get("/case-studies", response_model=list[WebsiteCaseStudyOut])
async def list_public_case_studies(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List all published case studies."""
    try:
        query = select(WebsiteCaseStudy).where(WebsiteCaseStudy.is_published.is_(True))
        if category and category.strip().lower() != "all":
            query = query.where(WebsiteCaseStudy.category.ilike(category.strip()))

        rows = (
            await db.execute(
                query.order_by(WebsiteCaseStudy.display_order.asc(), WebsiteCaseStudy.created_at.desc())
            )
        ).scalars().all()
        return [await _serialize_public_cs(db, r) for r in rows]
    except Exception:
        return []


@router.get("/case-studies/{slug}", response_model=WebsiteCaseStudyOut)
async def get_public_case_study_by_slug(slug: str, db: AsyncSession = Depends(get_db)):
    """Get a single published case study by slug."""
    clean = (slug or "").strip().lower()
    row = (
        await db.execute(
            select(WebsiteCaseStudy).where(
                WebsiteCaseStudy.slug == clean,
                WebsiteCaseStudy.is_published.is_(True),
            )
        )
    ).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Case study not found")
    return await _serialize_public_cs(db, row)
