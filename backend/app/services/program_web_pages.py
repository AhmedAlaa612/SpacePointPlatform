"""Lifecycle services for Program Landing Pages (WebsiteEvent) and
Program/Multi-Cohort Case Studies (WebsiteCaseStudy).
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.program import Program
from app.models.spine.organization import Organization
from app.models.website_case_study import WebsiteCaseStudy
from app.models.website_event import WebsiteEvent
from app.services.program_web_live import (
    PROGRAM_TO_EVENT_TYPE,
    invalidate_program_web_cache,
    resolve_case_study_live,
)
from app.services.website_case_studies import unique_case_study_slug
from app.services.website_events import unique_website_event_slug

logger = logging.getLogger(__name__)


async def ensure_program_landing_draft(
    db: AsyncSession,
    program: Program,
    *,
    created_by_user_id: UUID | None = None,
    commit: bool = False,
) -> WebsiteEvent:
    """Idempotently ensure a Program has a linked WebsiteEvent landing page draft."""
    existing = (
        await db.execute(select(WebsiteEvent).where(WebsiteEvent.program_id == program.id))
    ).scalars().first()
    if existing is not None:
        if not existing.preview_token:
            existing.preview_token = secrets.token_urlsafe(24)
            if commit:
                await db.commit()
                await db.refresh(existing)
        return existing

    country = "uae"
    host_org_name = "SpacePoint"
    if program.organization_id:
        org = await db.get(Organization, program.organization_id)
        if org:
            raw_c = (org.country or "uae").strip().lower()
            country = "uae" if raw_c in ("", "ae") else raw_c
            host_org_name = org.name_latin or org.name_arabic or "Partner Organization"

    slug = await unique_website_event_slug(db, program.name)
    ev = WebsiteEvent(
        slug=slug,
        program_id=program.id,
        organization_id=program.organization_id,
        created_by_user_id=created_by_user_id,
        country=country,
        event_type=PROGRAM_TO_EVENT_TYPE.get((program.program_type or "").lower(), "workshop"),
        title=program.name,
        banner_url="/assets/img/default-event-hero.jpg",
        about_text=program.description,
        host_org_name=host_org_name,
        live_linked=True,
        overrides={},
        hidden_cohort_ids=[],
        hidden_sections=[],
        preview_token=secrets.token_urlsafe(24),
        is_published=False,
        default_language="en",
        ar_content={},
    )
    db.add(ev)
    if commit:
        await db.commit()
        await db.refresh(ev)
    else:
        await db.flush()
    invalidate_program_web_cache(program.id)
    return ev


async def safe_ensure_program_landing_draft(
    db: AsyncSession,
    program: Program,
    *,
    created_by_user_id: UUID | None = None,
) -> None:
    """Lifecycle hook wrapper: never breaks program creation if landing draft fails."""
    if (program.name or "").strip().lower().startswith("[template]"):
        return
    try:
        await ensure_program_landing_draft(
            db,
            program,
            created_by_user_id=created_by_user_id,
            commit=True,
        )
    except Exception:
        logger.warning(
            "Failed to auto-draft WebsiteEvent landing page for program %s",
            program.id,
            exc_info=True,
        )


async def create_case_study_from_program(
    db: AsyncSession,
    *,
    program: Program,
    cohort_ids: list[UUID],
    title: str | None = None,
    include_buckets: list[str] | None = None,
) -> WebsiteCaseStudy:
    """Create a hybrid-live draft WebsiteCaseStudy linked to a Program + ordered Cohorts."""
    ordered_str = [str(cid) for cid in cohort_ids]
    source_type = (
        "multi_cohort"
        if len(ordered_str) > 1
        else ("cohort" if len(ordered_str) == 1 else "program")
    )
    live = await resolve_case_study_live(
        db,
        source_type=source_type,
        program_id=program.id,
        cohort_id=cohort_ids[0] if len(cohort_ids) == 1 else None,
        cohort_ids=ordered_str,
    )

    final_title = (title or "").strip() or live["title"] or program.name
    slug = await unique_case_study_slug(db, final_title)

    # Determine hidden sections from include_buckets if explicitly specified
    hidden_sections: list[str] = []
    if include_buckets is not None:
        inc = set(include_buckets)
        for sec in ("metrics", "curriculum", "structure", "partners"):
            if sec not in inc:
                hidden_sections.append(sec)

    overrides: dict[str, object] = {}
    if title and title.strip() and title.strip() != live["title"]:
        overrides["title"] = title.strip()

    cs = WebsiteCaseStudy(
        slug=slug,
        title=final_title,
        subtitle=live.get("subtitle"),
        category=live.get("category") or "National Programs",
        card_summary=live.get("card_summary") or f"Hands-on mission program: {final_title}.",
        cover_image_url="",
        partner_name=live.get("partner_name"),
        source_type=source_type,
        program_id=program.id,
        cohort_id=cohort_ids[0] if len(cohort_ids) == 1 else None,
        cohort_ids=ordered_str,
        partners=live.get("partners") or [],
        overview_text=live.get("overview_text"),
        metrics=live.get("metrics") or [],
        card_metrics=live.get("card_metrics") or [],
        curriculum_chapters=live.get("curriculum_chapters") or [],
        structure_sections=live.get("structure_sections") or [],
        live_linked=True,
        overrides=overrides,
        hidden_sections=hidden_sections,
        preview_token=secrets.token_urlsafe(24),
        is_published=False,
        is_featured=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(cs)
    await db.commit()
    await db.refresh(cs)
    invalidate_program_web_cache(program.id)
    return cs
