"""Contacts admin + organizations endpoints (V2 R2-4). Mounted at /spine — no
/api prefix anywhere in this codebase (VERIFIED against app/main.py: every
router mounts at root). Every route requires the operations role (or admin,
which RequireRole always lets through) — only merge resolution
(routers/spine/merge_reviews.py) is admin-only.

`q` is a plain case-insensitive substring search over name/email/phone —
nothing here does name-similarity matching or scoring. `full_name` exists
purely for a human to read and search by; the identity-matching service
(services/spine/identity.py) never reads it, and this router doesn't add a
name-based shortcut either.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.spine.contact import Contact, ContactRelationship
from app.models.spine.contact_role_event import ContactRoleEvent
from app.models.spine.organization import Organization
from app.models.user import User
from app.schemas.spine.contacts import (
    ContactBrief,
    ContactDetail,
    ContactListItem,
    ContactRelationshipCreate,
    ContactRelationshipOut,
    ContactRoleEventOut,
    ContactSearchResponse,
    ContactUpdate,
    OrganizationCreate,
    OrganizationOut,
    OrganizationUpdate,
)
from app.services.spine.identity import resolve_or_create_organization
from app.services.spine.role_history import record_role_diff

router = APIRouter(prefix="/spine", tags=["spine-contacts"])


async def _build_contact_detail(db: AsyncSession, contact: Contact) -> ContactDetail:
    organization_name = None
    if contact.organization_id:
        org = await db.get(Organization, contact.organization_id)
        organization_name = org.name_latin if org else None

    outgoing = (await db.execute(
        select(ContactRelationship).where(ContactRelationship.contact_id == contact.id)
    )).scalars().all()
    incoming = (await db.execute(
        select(ContactRelationship).where(ContactRelationship.related_contact_id == contact.id)
    )).scalars().all()

    other_ids = {r.related_contact_id for r in outgoing} | {r.contact_id for r in incoming}
    other_contacts: dict[uuid.UUID, Contact] = {}
    if other_ids:
        rows = (await db.execute(select(Contact).where(Contact.id.in_(other_ids)))).scalars().all()
        other_contacts = {c.id: c for c in rows}

    relationships: list[ContactRelationshipOut] = []
    for r in outgoing:
        other = other_contacts.get(r.related_contact_id)
        relationships.append(ContactRelationshipOut(
            id=r.id, contact_id=r.contact_id, related_contact_id=r.related_contact_id,
            relation=r.relation, created_at=r.created_at, direction="outgoing",
            other_contact=ContactBrief.model_validate(other) if other else None,
        ))
    for r in incoming:
        other = other_contacts.get(r.contact_id)
        relationships.append(ContactRelationshipOut(
            id=r.id, contact_id=r.contact_id, related_contact_id=r.related_contact_id,
            relation=r.relation, created_at=r.created_at, direction="incoming",
            other_contact=ContactBrief.model_validate(other) if other else None,
        ))

    return ContactDetail(
        id=contact.id,
        full_name=contact.full_name,
        contact_roles=contact.contact_roles or [],
        primary_phone_e164=contact.primary_phone_e164,
        whatsapp_e164=contact.whatsapp_e164,
        secondary_phones=contact.secondary_phones or [],
        email=contact.email,
        preferred_language=contact.preferred_language,
        country=contact.country,
        city=contact.city,
        date_of_birth=contact.date_of_birth,
        grade=contact.grade,
        lifecycle_stage=contact.lifecycle_stage,
        owner_user_id=contact.owner_user_id,
        organization_id=contact.organization_id,
        organization_name=organization_name,
        merged_into_id=contact.merged_into_id,
        notes=contact.notes,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
        relationships=relationships,
    )


@router.get("/contacts", response_model=ContactSearchResponse)
async def search_contacts(
    q: str | None = None,
    role: str | None = None,
    lifecycle_stage: str | None = None,
    country: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    # Merged-away duplicates are soft-retired (merged_into_id set) — exclude
    # them from search by default so the list shows live/canonical contacts.
    stmt = select(Contact).where(Contact.merged_into_id.is_(None))
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Contact.full_name.ilike(pattern),
                Contact.email.ilike(pattern),
                Contact.primary_phone_e164.ilike(pattern),
            )
        )
    if role:
        stmt = stmt.where(Contact.contact_roles.any(role))
    if lifecycle_stage:
        stmt = stmt.where(Contact.lifecycle_stage == lifecycle_stage)
    if country:
        stmt = stmt.where(Contact.country == country)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    stmt = stmt.order_by(Contact.created_at.desc(), Contact.id.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()

    return ContactSearchResponse(
        items=[ContactListItem.model_validate(c) for c in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/contacts/{contact_id}", response_model=ContactDetail)
async def get_contact(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    contact = await db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return await _build_contact_detail(db, contact)


@router.patch("/contacts/{contact_id}", response_model=ContactDetail)
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_operations),
):
    contact = await db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Contact not found")

    updates = body.model_dump(exclude_unset=True)
    roles_before = list(contact.contact_roles or []) if "contact_roles" in updates else None

    # Not a real column — resolve-or-create by name, gap-fill only (a blank
    # value never clears an existing organization_id).
    organization_name = (updates.pop("organization_name", None) or "").strip() or None
    if organization_name:
        org = await resolve_or_create_organization(db, organization_name)
        contact.organization_id = org.id

    for field, value in updates.items():
        setattr(contact, field, value)

    if roles_before is not None:
        await record_role_diff(
            db, contact.id, roles_before, contact.contact_roles,
            source="contact_edit", changed_by_user_id=actor.id,
        )

    await db.commit()
    await db.refresh(contact)
    return await _build_contact_detail(db, contact)


@router.get("/contacts/{contact_id}/role-history", response_model=list[ContactRoleEventOut])
async def get_contact_role_history(
    contact_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """The dated timeline behind "when did this person become an instructor"
    (operator request, 2026-07-24) — every role this contact has gained or
    lost, oldest first, across every source (registration, desk, import,
    a direct contact edit, or a staff role change on their linked user
    account). See services/spine/role_history.py."""
    contact = await db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Contact not found")

    rows = (await db.execute(
        select(ContactRoleEvent, User.full_name)
        .outerjoin(User, User.id == ContactRoleEvent.changed_by_user_id)
        .where(ContactRoleEvent.contact_id == contact_id)
        .order_by(ContactRoleEvent.occurred_at.asc())
    )).all()

    return [
        ContactRoleEventOut(
            id=event.id, role=event.role, action=event.action, source=event.source,
            changed_by_user_id=event.changed_by_user_id, changed_by_name=changed_by_name,
            occurred_at=event.occurred_at,
        )
        for event, changed_by_name in rows
    ]


@router.post(
    "/contacts/{contact_id}/relationships",
    response_model=ContactRelationshipOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_relationship(
    contact_id: uuid.UUID,
    body: ContactRelationshipCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    contact = await db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Contact not found")
    if body.related_contact_id == contact_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="A contact cannot be related to itself")
    related = await db.get(Contact, body.related_contact_id)
    if related is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Related contact not found")

    # Check the model's UniqueConstraint on (contact_id, related_contact_id,
    # relation) up front so a duplicate is a clean 409, not a raw IntegrityError.
    existing = (await db.execute(
        select(ContactRelationship).where(
            ContactRelationship.contact_id == contact_id,
            ContactRelationship.related_contact_id == body.related_contact_id,
            ContactRelationship.relation == body.relation,
        )
    )).scalars().first()
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This relationship already exists")

    rel = ContactRelationship(
        id=uuid.uuid4(),
        contact_id=contact_id,
        related_contact_id=body.related_contact_id,
        relation=body.relation,
    )
    db.add(rel)
    await db.commit()
    await db.refresh(rel)

    return ContactRelationshipOut(
        id=rel.id, contact_id=rel.contact_id, related_contact_id=rel.related_contact_id,
        relation=rel.relation, created_at=rel.created_at, direction="outgoing",
        other_contact=ContactBrief.model_validate(related),
    )


# ── Organizations ────────────────────────────────────────────────────────

@router.get("/organizations", response_model=list[OrganizationOut])
async def list_organizations(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    stmt = select(Organization).order_by(Organization.name_latin.asc())
    if q:
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(or_(Organization.name_latin.ilike(pattern), Organization.name_arabic.ilike(pattern)))
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


@router.post("/organizations", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrganizationCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    org = Organization(id=uuid.uuid4(), **body.model_dump())
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return org


@router.get("/organizations/{org_id}", response_model=OrganizationOut)
async def get_organization(
    org_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.patch("/organizations/{org_id}", response_model=OrganizationOut)
async def update_organization(
    org_id: uuid.UUID,
    body: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Organization not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(org, field, value)

    await db.commit()
    await db.refresh(org)
    return org
