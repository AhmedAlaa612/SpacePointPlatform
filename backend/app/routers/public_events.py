from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.website_event import MegaEvent, WebsiteEvent
from app.services.website_events import (
    ensure_default_events_seeded,
    serialize_mega_events,
    serialize_website_events,
)

router = APIRouter(prefix="/public/website/events", tags=["public-website-events"])


@router.get("")
async def list_public_events(
    country: str | None = Query(default=None),
    mega_event_slug: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Public directory of published MegaEvents and WebsiteEvents, with optional
    country and mega_event_slug filters."""
    await ensure_default_events_seeded(db)

    all_megas = (
        await db.execute(
            select(MegaEvent)
            .where(MegaEvent.is_published.is_(True))
            .order_by(MegaEvent.display_order.asc(), MegaEvent.created_at.desc())
        )
    ).scalars().all()

    all_events = (
        await db.execute(
            select(WebsiteEvent)
            .where(WebsiteEvent.is_published.is_(True))
            .order_by(WebsiteEvent.display_order.asc(), WebsiteEvent.created_at.desc())
        )
    ).scalars().all()

    countries_set = {"uae"}
    for m in all_megas:
        if m.country:
            countries_set.add(m.country.strip().lower())
    for e in all_events:
        if e.country:
            countries_set.add(e.country.strip().lower())

    norm_country = country.strip().lower() if country and country.strip() else None
    if norm_country and norm_country != "all":
        filtered_megas = [m for m in all_megas if (m.country or "").strip().lower() == norm_country]
        filtered_events = [e for e in all_events if (e.country or "").strip().lower() == norm_country]
    else:
        filtered_megas = list(all_megas)
        filtered_events = list(all_events)

    if mega_event_slug and mega_event_slug.strip():
        target_slug = mega_event_slug.strip().lower()
        target_mega = next((m for m in all_megas if m.slug.lower() == target_slug), None)
        if target_mega:
            filtered_events = [e for e in filtered_events if e.mega_event_id == target_mega.id]
        else:
            filtered_events = []

    return {
        "countries": sorted(countries_set),
        "mega_events": await serialize_mega_events(db, filtered_megas, published_only_counts=True),
        "events": await serialize_website_events(db, filtered_events),
    }


@router.get("/resolve/{slug}")
async def resolve_public_event_or_mega(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Resolves a slug on `/events/{country}/{slug}` or `/events/{slug}` to either
    a published MegaEvent (plus its published child WebsiteEvents) or a published
    WebsiteEvent (plus its parent MegaEvent summary if linked)."""
    await ensure_default_events_seeded(db)
    clean_slug = slug.strip().lower()

    mega = (
        await db.execute(
            select(MegaEvent).where(
                MegaEvent.slug == clean_slug,
                MegaEvent.is_published.is_(True),
            )
        )
    ).scalars().first()
    if mega is not None:
        children = (
            await db.execute(
                select(WebsiteEvent)
                .where(
                    WebsiteEvent.mega_event_id == mega.id,
                    WebsiteEvent.is_published.is_(True),
                )
                .order_by(WebsiteEvent.display_order.asc(), WebsiteEvent.created_at.desc())
            )
        ).scalars().all()
        mega_serialized = (await serialize_mega_events(db, [mega], published_only_counts=True))[0]
        return {
            "kind": "mega_event",
            "mega_event": mega_serialized,
            "events": await serialize_website_events(db, children),
        }

    ev = (
        await db.execute(
            select(WebsiteEvent).where(
                WebsiteEvent.slug == clean_slug,
                WebsiteEvent.is_published.is_(True),
            )
        )
    ).scalars().first()
    if ev is not None:
        ev_serialized = (await serialize_website_events(db, [ev]))[0]
        parent_mega = None
        if ev.mega_event_id:
            pm = await db.get(MegaEvent, ev.mega_event_id)
            if pm and pm.is_published:
                parent_mega = (await serialize_mega_events(db, [pm], published_only_counts=True))[0]
        return {
            "kind": "event",
            "event": ev_serialized,
            "mega_event": parent_mega,
        }

    raise HTTPException(status_code=404, detail="Event not found")
