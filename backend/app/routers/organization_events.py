from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_organization_account
from app.db.session import get_db
from app.models.spine.organization import Organization
from app.models.user import User
from app.models.website_event import MegaEvent, WebsiteEvent
from app.schemas.website_event import (
    WebsiteEventCreate,
    WebsiteEventOut,
    WebsiteEventUpdate,
)
from app.services.website_events import (
    ensure_default_events_seeded,
    resolve_user_organization,
    serialize_mega_events,
    serialize_website_events,
    unique_website_event_slug,
)

router = APIRouter(prefix="/organization", tags=["organization-events"])


def _is_admin_or_ops(user: User) -> bool:
    return any(r in user.role_values for r in ("admin", "operations"))


@router.get("/me")
async def get_my_organization_context(
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Returns the organization linked to the current user and all available
    MegaEvents they can attach their events to."""
    await ensure_default_events_seeded(db)
    org = await resolve_user_organization(db, current_user)
    megas = (
        await db.execute(
            select(MegaEvent)
            .where(MegaEvent.is_published.is_(True))
            .order_by(MegaEvent.display_order.asc(), MegaEvent.title.asc())
        )
    ).scalars().all()
    return {
        "organization": {
            "id": str(org.id),
            "name_latin": org.name_latin,
            "name_arabic": org.name_arabic,
            "org_type": org.org_type,
            "country": org.country,
            "city": org.city,
        }
        if org
        else None,
        "mega_events": await serialize_mega_events(db, megas, published_only_counts=True),
    }


@router.get("/events", response_model=list[WebsiteEventOut])
async def list_my_organization_events(
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    await ensure_default_events_seeded(db)
    org = await resolve_user_organization(db, current_user)
    if _is_admin_or_ops(current_user) and org is None:
        rows = (
            await db.execute(
                select(WebsiteEvent).order_by(WebsiteEvent.display_order.asc(), WebsiteEvent.updated_at.desc())
            )
        ).scalars().all()
    else:
        conds = [WebsiteEvent.created_by_user_id == current_user.id]
        if org is not None:
            conds.append(WebsiteEvent.organization_id == org.id)
        rows = (
            await db.execute(
                select(WebsiteEvent)
                .where(or_(*conds))
                .order_by(WebsiteEvent.display_order.asc(), WebsiteEvent.updated_at.desc())
            )
        ).scalars().all()
    return await serialize_website_events(db, rows)


@router.post("/events", response_model=WebsiteEventOut, status_code=status.HTTP_201_CREATED)
async def create_organization_event(
    body: WebsiteEventCreate,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Organizations create their own events using the standard 12-section
    template. `is_published` is strictly forced to False for organization
    users — only Admin/Operations can publish or unpublish."""
    org = await resolve_user_organization(db, current_user)
    slug = await unique_website_event_slug(db, body.slug or body.title)

    data = body.model_dump(exclude={"slug", "is_published", "organization_id"})
    data["country"] = (data.get("country") or (org.country if org else "uae") or "uae").strip().lower()
    if not data.get("host_org_name") and org is not None:
        data["host_org_name"] = org.name_latin

    row = WebsiteEvent(
        **data,
        slug=slug,
        organization_id=org.id if org else body.organization_id,
        created_by_user_id=current_user.id,
        is_published=bool(body.is_published) if _is_admin_or_ops(current_user) else False,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return (await serialize_website_events(db, [row]))[0]


@router.put("/events/{event_id}", response_model=WebsiteEventOut)
async def update_organization_event(
    event_id: UUID,
    body: WebsiteEventUpdate,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(WebsiteEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")

    org = await resolve_user_organization(db, current_user)
    is_owner = (
        _is_admin_or_ops(current_user)
        or row.created_by_user_id == current_user.id
        or (org is not None and row.organization_id == org.id)
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="Not permitted to edit this event")

    updates = body.model_dump(exclude_unset=True)
    # Organization accounts can never self-publish/unpublish or reassign org ownership
    if not _is_admin_or_ops(current_user):
        updates.pop("is_published", None)
        updates.pop("organization_id", None)

    if "slug" in updates and updates["slug"]:
        updates["slug"] = await unique_website_event_slug(db, updates["slug"], exclude_id=row.id)
    if "country" in updates and updates["country"]:
        updates["country"] = updates["country"].strip().lower()

    for k, v in updates.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(row)
    return (await serialize_website_events(db, [row]))[0]


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization_event(
    event_id: UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(WebsiteEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")

    org = await resolve_user_organization(db, current_user)
    is_owner = (
        _is_admin_or_ops(current_user)
        or row.created_by_user_id == current_user.id
        or (org is not None and row.organization_id == org.id)
    )
    if not is_owner:
        raise HTTPException(status_code=403, detail="Not permitted to delete this event")

    await db.delete(row)
    await db.commit()
    return None
