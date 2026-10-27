from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_website_admin
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.spine.organization import Organization
from app.models.user import User
from app.models.website_event import MegaEvent, WebsiteEvent
from app.schemas.website_event import (
    MegaEventCreate,
    MegaEventOut,
    MegaEventUpdate,
    OrganizationAccountCreateIn,
    OrganizationSummaryOut,
    WebsiteEventCreate,
    WebsiteEventOut,
    WebsiteEventUpdate,
)
from app.services.documents.id_card import ensure_card_number
from app.services.spine.identity import (
    normalize_user_email,
    resolve_or_create_contact,
    user_email_matches,
)
from app.services.website_events import (
    ensure_default_events_seeded,
    serialize_mega_events,
    serialize_website_events,
    unique_mega_event_slug,
    unique_website_event_slug,
)

router = APIRouter(prefix="/website", tags=["admin-website-events"])


class PublishToggleIn(BaseModel):
    is_published: bool


# ── Mega Events CRUD ─────────────────────────────────────────────────────────
@router.get("/mega-events", response_model=list[MegaEventOut])
async def admin_list_mega_events(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    await ensure_default_events_seeded(db)
    rows = (
        await db.execute(
            select(MegaEvent).order_by(MegaEvent.display_order.asc(), MegaEvent.created_at.desc())
        )
    ).scalars().all()
    return await serialize_mega_events(db, rows, published_only_counts=False)


@router.post("/mega-events", response_model=MegaEventOut, status_code=status.HTTP_201_CREATED)
async def admin_create_mega_event(
    body: MegaEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    slug = await unique_mega_event_slug(db, body.slug or body.title)
    data = body.model_dump(exclude={"slug"})
    data["country"] = (data.get("country") or "uae").strip().lower()
    row = MegaEvent(**data, slug=slug)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return (await serialize_mega_events(db, [row]))[0]


@router.put("/mega-events/{mega_id}", response_model=MegaEventOut)
async def admin_update_mega_event(
    mega_id: UUID,
    body: MegaEventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = await db.get(MegaEvent, mega_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Mega event not found")
    updates = body.model_dump(exclude_unset=True)
    if "slug" in updates and updates["slug"]:
        updates["slug"] = await unique_mega_event_slug(db, updates["slug"], exclude_id=row.id)
    if "country" in updates and updates["country"]:
        updates["country"] = updates["country"].strip().lower()
    for k, v in updates.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return (await serialize_mega_events(db, [row]))[0]


@router.delete("/mega-events/{mega_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_mega_event(
    mega_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = await db.get(MegaEvent, mega_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Mega event not found")
    await db.delete(row)
    await db.commit()
    return None


# ── Website Events CRUD & Publishing ─────────────────────────────────────────
@router.get("/events", response_model=list[WebsiteEventOut])
async def admin_list_website_events(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    await ensure_default_events_seeded(db)
    rows = (
        await db.execute(
            select(WebsiteEvent).order_by(
                WebsiteEvent.display_order.asc(),
                WebsiteEvent.updated_at.desc(),
            )
        )
    ).scalars().all()
    return await serialize_website_events(db, rows)


@router.post("/events", response_model=WebsiteEventOut, status_code=status.HTTP_201_CREATED)
async def admin_create_website_event(
    body: WebsiteEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    slug = await unique_website_event_slug(db, body.slug or body.title)
    data = body.model_dump(exclude={"slug"})
    data["country"] = (data.get("country") or "uae").strip().lower()
    if data.get("organization_id") and not data.get("host_org_name"):
        org = await db.get(Organization, data["organization_id"])
        if org:
            data["host_org_name"] = org.name_latin
    row = WebsiteEvent(**data, slug=slug, created_by_user_id=current_user.id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return (await serialize_website_events(db, [row]))[0]


@router.put("/events/{event_id}", response_model=WebsiteEventOut)
async def admin_update_website_event(
    event_id: UUID,
    body: WebsiteEventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = await db.get(WebsiteEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    updates = body.model_dump(exclude_unset=True)
    if "slug" in updates and updates["slug"]:
        updates["slug"] = await unique_website_event_slug(db, updates["slug"], exclude_id=row.id)
    if "country" in updates and updates["country"]:
        updates["country"] = updates["country"].strip().lower()
    if "organization_id" in updates and updates["organization_id"] and not updates.get("host_org_name"):
        org = await db.get(Organization, updates["organization_id"])
        if org and not row.host_org_name:
            updates["host_org_name"] = org.name_latin
    for k, v in updates.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return (await serialize_website_events(db, [row]))[0]


@router.post("/events/{event_id}/publish", response_model=WebsiteEventOut)
async def admin_toggle_publish_event(
    event_id: UUID,
    body: PublishToggleIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = await db.get(WebsiteEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    row.is_published = body.is_published
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return (await serialize_website_events(db, [row]))[0]


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_website_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = await db.get(WebsiteEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.delete(row)
    await db.commit()
    return None


# ── Organization Accounts & Event Assignment ─────────────────────────────────
@router.get("/organizations", response_model=list[OrganizationSummaryOut])
async def admin_list_event_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    orgs = (
        await db.execute(select(Organization).order_by(Organization.name_latin.asc()))
    ).scalars().all()
    if not orgs:
        return []

    owner_ids = {o.owner_user_id for o in orgs if o.owner_user_id}
    owners_by_id: dict[UUID, User] = {}
    if owner_ids:
        users = (await db.execute(select(User).where(User.id.in_(owner_ids)))).scalars().all()
        owners_by_id = {u.id: u for u in users}

    counts = dict(
        (
            await db.execute(
                select(WebsiteEvent.organization_id, func.count(WebsiteEvent.id))
                .where(WebsiteEvent.organization_id.is_not(None))
                .group_by(WebsiteEvent.organization_id)
            )
        ).all()
    )

    member_counts = dict(
        (
            await db.execute(
                select(User.organization_id, func.count(User.id))
                .where(User.organization_id.is_not(None))
                .group_by(User.organization_id)
            )
        ).all()
    )

    out = []
    for o in orgs:
        owner = owners_by_id.get(o.owner_user_id) if o.owner_user_id else None
        m_count = member_counts.get(o.id, 1 if o.owner_user_id else 0)
        out.append(
            {
                "id": o.id,
                "name_latin": o.name_latin,
                "name_arabic": o.name_arabic,
                "org_type": o.org_type,
                "country": o.country,
                "city": o.city,
                "owner_user_id": o.owner_user_id,
                "owner_email": owner.email if owner else None,
                "owner_name": owner.full_name if owner else None,
                "owner_phone": owner.phone if owner else None,
                "owner_status": owner.status if owner else None,
                "events_count": counts.get(o.id, 0),
                "members_count": max(m_count, 1 if o.owner_user_id else 0),
                "is_approved": o.is_approved,
                "can_publish_events": o.can_publish_events,
                "can_author_courses": o.can_author_courses,
                "can_publish_courses": o.can_publish_courses,
                "course_scope_all": o.course_scope_all,
                "allowed_course_ids": [str(c) for c in (o.allowed_course_ids or [])],
                "max_events": o.max_events,
                "max_programs": o.max_programs,
                "max_cohorts": o.max_cohorts,
                "max_students_per_cohort": o.max_students_per_cohort,
                "max_observers_per_cohort": o.max_observers_per_cohort,
            }
        )
    return out


@router.post("/organizations/account", response_model=OrganizationSummaryOut, status_code=status.HTTP_201_CREATED)
async def admin_create_organization_account(
    body: OrganizationAccountCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """Admin creates an Organization and a portal login account (`organization`
    role) so the organization can log in, create events, and edit assigned events."""
    email = normalize_user_email(body.email)
    existing_user = (
        await db.execute(select(User).where(user_email_matches(email)))
    ).scalars().first()

    if existing_user is not None:
        if "organization" not in existing_user.role_values:
            existing_user.roles = list(existing_user.roles or []) + [UserRole.organization]
        user = existing_user
        contact_id = existing_user.contact_id
    else:
        contact, _ = await resolve_or_create_contact(
            db,
            full_name=body.full_name.strip(),
            phone=(body.phone or "").strip() or None,
            email=email,
            contact_roles=["sponsor_rep"],
            role_event_source="admin_organization_account",
            country=(body.country or "uae").strip().lower(),
            city=(body.city or "").strip() or None,
        )
        contact_id = contact.id
        user = User(
            full_name=body.full_name.strip(),
            email=email,
            password_hash=get_password_hash(body.password),
            roles=[UserRole.organization],
            status="active",
            must_change_password=False,
            contact_id=contact.id,
            phone=(body.phone or "").strip() or None,
            country=(body.country or "uae").strip().lower(),
            city_other=(body.city or "").strip() or None,
        )
        db.add(user)
        await db.flush()
        await ensure_card_number(db, user)

    org = Organization(
        name_latin=body.org_name_latin.strip(),
        name_arabic=(body.org_name_arabic or "").strip() or None,
        org_type=(body.org_type or "university").strip().lower(),
        country=(body.country or "uae").strip().lower(),
        city=(body.city or "").strip() or None,
        primary_contact_id=contact_id,
        owner_user_id=user.id,
        is_approved=body.is_approved,
        can_publish_events=body.can_publish_events,
        can_author_courses=body.can_author_courses,
        can_publish_courses=body.can_publish_courses,
        course_scope_all=body.course_scope_all,
        allowed_course_ids=body.allowed_course_ids,
        max_events=body.max_events,
        max_programs=body.max_programs,
        max_cohorts=body.max_cohorts,
        max_students_per_cohort=body.max_students_per_cohort,
        max_observers_per_cohort=body.max_observers_per_cohort,
    )
    db.add(org)
    await db.flush()
    user.organization_id = org.id
    await db.commit()
    await db.refresh(org)

    return {
        "id": org.id,
        "name_latin": org.name_latin,
        "name_arabic": org.name_arabic,
        "org_type": org.org_type,
        "country": org.country,
        "city": org.city,
        "owner_user_id": user.id,
        "owner_email": user.email,
        "owner_name": user.full_name,
        "owner_phone": user.phone,
        "owner_status": user.status,
        "events_count": 0,
        "members_count": 1,
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


@router.put("/organizations/{org_id}", response_model=OrganizationSummaryOut)
async def admin_update_organization_account(
    org_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    from app.schemas.website_event import OrganizationAccountUpdateIn
    from app.services.spine.identity import replace_user_email

    payload = OrganizationAccountUpdateIn.model_validate(body)
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    if payload.org_name_latin is not None and payload.org_name_latin.strip():
        org.name_latin = payload.org_name_latin.strip()
    if payload.org_name_arabic is not None:
        org.name_arabic = payload.org_name_arabic.strip() or None
    if payload.org_type is not None and payload.org_type.strip():
        org.org_type = payload.org_type.strip().lower()
    if payload.country is not None:
        org.country = payload.country.strip().lower() or None
    if payload.city is not None:
        org.city = payload.city.strip() or None

    if payload.is_approved is not None:
        org.is_approved = payload.is_approved
        from app.models.application import Application
        app_rows = (await db.execute(
            select(Application).where(Application.role == "organization")
        )).scalars().all()
        for a in app_rows:
            if (a.answers or {}).get("organization_id") == str(org.id):
                if payload.is_approved and a.status == "pending":
                    a.status = "approved"
                    a.reviewed_at = datetime.now(timezone.utc)
                    a.reviewed_by = current_user.id
                elif not payload.is_approved and a.status == "approved":
                    a.status = "rejected"
                    a.reviewed_at = datetime.now(timezone.utc)
                    a.reviewed_by = current_user.id
    if payload.can_publish_events is not None:
        org.can_publish_events = payload.can_publish_events
    if payload.can_author_courses is not None:
        org.can_author_courses = payload.can_author_courses
    if payload.can_publish_courses is not None:
        org.can_publish_courses = payload.can_publish_courses
    if payload.course_scope_all is not None:
        org.course_scope_all = payload.course_scope_all
    if payload.allowed_course_ids is not None:
        org.allowed_course_ids = payload.allowed_course_ids
    if "max_events" in body:
        org.max_events = payload.max_events
    if "max_programs" in body:
        org.max_programs = payload.max_programs
    if "max_cohorts" in body:
        org.max_cohorts = payload.max_cohorts
    if "max_students_per_cohort" in body:
        org.max_students_per_cohort = payload.max_students_per_cohort
    if "max_observers_per_cohort" in body:
        org.max_observers_per_cohort = payload.max_observers_per_cohort

    owner = await db.get(User, org.owner_user_id) if org.owner_user_id else None
    if owner is not None:
        if payload.full_name is not None and payload.full_name.strip():
            owner.full_name = payload.full_name.strip()
        if payload.phone is not None:
            owner.phone = payload.phone.strip() or None
        if payload.email is not None and payload.email.strip():
            new_email = normalize_user_email(payload.email)
            clash = (
                await db.execute(
                    select(User).where(user_email_matches(new_email), User.id != owner.id)
                )
            ).scalars().first()
            if clash is not None:
                raise HTTPException(status_code=409, detail="Email already registered")
            await replace_user_email(db, owner, new_email)
            owner.email = new_email
        if payload.password is not None and payload.password.strip():
            owner.password_hash = get_password_hash(payload.password.strip())
            owner.must_change_password = False
    elif payload.email and payload.password:
        # Link/create a login user for an organization that previously had none
        email = normalize_user_email(payload.email)
        existing_user = (
            await db.execute(select(User).where(user_email_matches(email)))
        ).scalars().first()
        if existing_user is not None:
            if "organization" not in existing_user.role_values:
                existing_user.roles = list(existing_user.roles or []) + [UserRole.organization]
            owner = existing_user
        else:
            contact, _ = await resolve_or_create_contact(
                db,
                full_name=(payload.full_name or org.name_latin).strip(),
                phone=(payload.phone or "").strip() or None,
                email=email,
                contact_roles=["sponsor_rep"],
                role_event_source="admin_organization_account",
                country=org.country or "uae",
                city=org.city,
            )
            owner = User(
                full_name=(payload.full_name or org.name_latin).strip(),
                email=email,
                password_hash=get_password_hash(payload.password.strip()),
                roles=[UserRole.organization],
                status="active",
                must_change_password=False,
                contact_id=contact.id,
                phone=(payload.phone or "").strip() or None,
                country=org.country or "uae",
                city_other=org.city,
            )
            db.add(owner)
            await db.flush()
            await ensure_card_number(db, owner)
        org.owner_user_id = owner.id
        owner.organization_id = org.id
    elif owner is not None and owner.organization_id is None:
        owner.organization_id = org.id

    await db.commit()
    await db.refresh(org)
    if owner is not None:
        await db.refresh(owner)

    events_count = (
        await db.execute(
            select(func.count(WebsiteEvent.id)).where(WebsiteEvent.organization_id == org.id)
        )
    ).scalar_one()

    members_count = (
        await db.execute(
            select(func.count(User.id)).where(User.organization_id == org.id)
        )
    ).scalar_one()

    return {
        "id": org.id,
        "name_latin": org.name_latin,
        "name_arabic": org.name_arabic,
        "org_type": org.org_type,
        "country": org.country,
        "city": org.city,
        "owner_user_id": owner.id if owner else None,
        "owner_email": owner.email if owner else None,
        "owner_name": owner.full_name if owner else None,
        "owner_phone": owner.phone if owner else None,
        "owner_status": owner.status if owner else None,
        "events_count": events_count,
        "members_count": max(members_count, 1 if owner else 0),
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


@router.delete("/organizations/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_organization_account(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    from sqlalchemy import text
    from app.services import user as user_service

    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    owner_id = org.owner_user_id
    await db.execute(
        text("UPDATE website_events SET organization_id = NULL WHERE organization_id = :oid"),
        {"oid": org_id},
    )
    await db.execute(
        text("UPDATE contacts SET organization_id = NULL WHERE organization_id = :oid"),
        {"oid": org_id},
    )
    cohort_cnt = (
        await db.execute(
            text("SELECT COUNT(*) FROM cohorts WHERE organization_id = :oid"),
            {"oid": org_id},
        )
    ).scalar_one()
    if cohort_cnt == 0:
        await db.delete(org)
    else:
        org.owner_user_id = None
    await db.commit()

    # If the linked user only holds the `organization` role, delete that user account too
    if owner_id is not None:
        owner = await db.get(User, owner_id)
        if owner is not None and owner.role_values == ["organization"]:
            try:
                await user_service.delete_user(db, owner_id)
            except Exception:
                pass
    return None


@router.post("/organizations/{org_id}/reset-link")
async def admin_organization_reset_link(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """Generates a 72-hour password reset/set link for the organization's user account."""
    from datetime import timedelta
    from app.core.config import settings
    from app.core.security import create_password_set_token

    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not org.owner_user_id:
        raise HTTPException(status_code=400, detail="This organization has no login account linked yet.")
    owner = await db.get(User, org.owner_user_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Linked user account not found.")

    token = create_password_set_token(owner.id, expires_delta=timedelta(days=3))
    base = (settings.FRONTEND_URL or "http://localhost:5173").rstrip("/")
    return {
        "organization_id": str(org.id),
        "user_id": str(owner.id),
        "email": owner.email,
        "reset_url": f"{base}/set-password?token={token}",
    }
