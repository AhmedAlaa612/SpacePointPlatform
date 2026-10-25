from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_organization_account
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.user import User
from app.models.website_event import MegaEvent, WebsiteEvent
from app.schemas.website_event import (
    OrgTeamMemberCreateIn,
    OrgTeamMemberOut,
    WebsiteEventCreate,
    WebsiteEventOut,
    WebsiteEventUpdate,
)
from app.services.documents.id_card import ensure_card_number
from app.services.spine.identity import normalize_user_email, resolve_or_create_contact, user_email_matches
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
            "is_approved": org.is_approved,
            "can_publish_events": org.can_publish_events,
            "can_author_courses": org.can_author_courses,
            "can_publish_courses": org.can_publish_courses,
            "course_scope_all": org.course_scope_all,
            "allowed_course_ids": [str(c) for c in (org.allowed_course_ids or [])],
            "max_events": org.max_events,
            "max_programs": org.max_programs,
            "max_cohorts": org.max_cohorts,
            "max_students_per_cohort": org.max_students_per_cohort,
            "max_observers_per_cohort": org.max_observers_per_cohort,
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
    template. `is_published` is governed by org.can_publish_events."""
    org = await resolve_user_organization(db, current_user)
    if org is not None and org.max_events is not None and not _is_admin_or_ops(current_user):
        existing_count = await db.scalar(
            select(func.count(WebsiteEvent.id)).where(WebsiteEvent.organization_id == org.id)
        )
        if (existing_count or 0) >= org.max_events:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your organization limit is {org.max_events} landing page(s). Contact the SpacePoint team to increase your limit.",
            )

    slug = await unique_website_event_slug(db, body.slug or body.title)

    data = body.model_dump(exclude={"slug", "is_published", "organization_id"})
    data["country"] = (data.get("country") or (org.country if org else "uae") or "uae").strip().lower()
    if not data.get("host_org_name") and org is not None:
        data["host_org_name"] = org.name_latin
    if body.cohort_id and not data.get("registration_url"):
        data["registration_url"] = f"/learn/programs/{body.cohort_id}"

    can_publish = _is_admin_or_ops(current_user) or (org is not None and bool(org.can_publish_events))

    row = WebsiteEvent(
        **data,
        slug=slug,
        organization_id=org.id if org else body.organization_id,
        created_by_user_id=current_user.id,
        is_published=bool(body.is_published) if can_publish else False,
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
    can_publish = _is_admin_or_ops(current_user) or (org is not None and bool(org.can_publish_events))
    if not can_publish:
        updates.pop("is_published", None)
    if not _is_admin_or_ops(current_user):
        updates.pop("organization_id", None)

    if "slug" in updates and updates["slug"]:
        updates["slug"] = await unique_website_event_slug(db, updates["slug"], exclude_id=row.id)
    if "country" in updates and updates["country"]:
        updates["country"] = updates["country"].strip().lower()
    if updates.get("cohort_id") and not updates.get("registration_url") and not row.registration_url:
        updates["registration_url"] = f"/learn/programs/{updates['cohort_id']}"

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


# ── Organization Team Management ─────────────────────────────────────────────
@router.get("/team", response_model=list[OrgTeamMemberOut])
async def list_my_organization_team(
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await resolve_user_organization(db, current_user)
    if org is None:
        return []
    conds = [User.organization_id == org.id]
    if org.owner_user_id:
        conds.append(User.id == org.owner_user_id)
    users = (
        await db.execute(
            select(User)
            .where(or_(*conds))
            .order_by(User.created_at.asc())
        )
    ).scalars().all()
    return [
        OrgTeamMemberOut(
            id=u.id,
            full_name=u.full_name,
            email=u.email,
            phone=u.phone,
            status=u.status,
            created_at=u.created_at,
            is_owner=(u.id == org.owner_user_id),
        )
        for u in users
    ]


@router.post("/team", response_model=OrgTeamMemberOut, status_code=status.HTTP_201_CREATED)
async def add_organization_team_member(
    body: OrgTeamMemberCreateIn,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await resolve_user_organization(db, current_user)
    if org is None:
        raise HTTPException(status_code=400, detail="No organization context found")

    email = normalize_user_email(body.email)
    existing = (
        await db.execute(select(User).where(user_email_matches(email)))
    ).scalars().first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    contact, _ = await resolve_or_create_contact(
        db,
        full_name=body.full_name.strip(),
        phone=(body.phone or "").strip() or None,
        email=email,
        contact_roles=["sponsor_rep"],
        role_event_source="org_team_member",
        country=org.country or "uae",
        city=org.city,
    )
    user = User(
        full_name=body.full_name.strip(),
        email=email,
        password_hash=get_password_hash(body.password),
        roles=[UserRole.organization],
        status="active",
        must_change_password=False,
        contact_id=contact.id if contact else None,
        organization_id=org.id,
        phone=(body.phone or "").strip() or None,
        country=org.country or "uae",
        city_other=org.city,
    )
    db.add(user)
    await db.flush()
    await ensure_card_number(db, user)
    await db.commit()
    await db.refresh(user)

    return OrgTeamMemberOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        status=user.status,
        created_at=user.created_at,
        is_owner=False,
    )


@router.delete("/team/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_organization_team_member(
    user_id: UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await resolve_user_organization(db, current_user)
    if org is None:
        raise HTTPException(status_code=400, detail="No organization context found")

    if user_id == org.owner_user_id:
        raise HTTPException(status_code=400, detail="Cannot remove the organization primary owner")

    user = await db.get(User, user_id)
    if user is None or user.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Team member not found")

    await db.delete(user)
    await db.commit()
    return None
