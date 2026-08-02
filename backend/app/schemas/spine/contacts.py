"""Schemas for the spine contacts admin + merge-review endpoints (V2 R2-4).

`ContactBrief` is the only shape used to describe a contact inside another
contact's payload (relationships, merge-review candidates) — it deliberately
carries just enough for a human to read and disambiguate (name in both
scripts, phone, email, roles). Nothing here computes or exposes a similarity
score between two contacts: name is never used for identity matching
anywhere in this system (see app/services/spine/identity.py's module
docstring) and this file doesn't add a UI-only backdoor for that.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, model_validator
from uuid import UUID


# ── Contact ──────────────────────────────────────────────────────────────

class ContactBrief(BaseModel):
    """Minimal contact shape for embedding — relationship's "other side",
    merge-review candidates. Just enough for a human to read."""

    id: UUID
    full_name: str
    contact_roles: list[str] = []
    primary_phone_e164: Optional[str] = None
    whatsapp_e164: Optional[str] = None
    email: Optional[str] = None
    lifecycle_stage: Optional[str] = None

    class Config:
        from_attributes = True


class ContactRelationshipOut(BaseModel):
    id: UUID
    contact_id: UUID
    related_contact_id: UUID
    relation: str
    created_at: datetime
    # "outgoing": this row's contact_id is the contact this was fetched under
    # (i.e. that contact -> other, via `relation`). "incoming": the reverse.
    direction: Literal["outgoing", "incoming"]
    other_contact: Optional[ContactBrief] = None

    class Config:
        from_attributes = True


class ContactListItem(BaseModel):
    id: UUID
    full_name: str
    contact_roles: list[str] = []
    primary_phone_e164: Optional[str] = None
    whatsapp_e164: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    lifecycle_stage: str
    organization_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ContactSearchResponse(BaseModel):
    items: list[ContactListItem]
    total: int
    limit: int
    offset: int


class ContactDetail(BaseModel):
    id: UUID
    full_name: str
    contact_roles: list[str] = []
    primary_phone_e164: Optional[str] = None
    whatsapp_e164: Optional[str] = None
    secondary_phones: list[str] = []
    email: Optional[str] = None
    preferred_language: str
    country: Optional[str] = None
    city: Optional[str] = None
    date_of_birth: Optional[date] = None
    grade: Optional[str] = None
    lifecycle_stage: str
    owner_user_id: Optional[UUID] = None
    organization_id: Optional[UUID] = None
    organization_name: Optional[str] = None
    merged_into_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    relationships: list[ContactRelationshipOut] = []

    class Config:
        from_attributes = True


class ContactUpdate(BaseModel):
    """Editable fields — PATCH /spine/contacts/{id}. All optional; only the
    fields present in the request body are applied (exclude_unset)."""

    full_name: Optional[str] = None
    contact_roles: Optional[list[str]] = None
    primary_phone_e164: Optional[str] = None
    whatsapp_e164: Optional[str] = None
    secondary_phones: Optional[list[str]] = None
    email: Optional[str] = None
    preferred_language: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    date_of_birth: Optional[date] = None
    grade: Optional[str] = None
    lifecycle_stage: Optional[str] = None
    owner_user_id: Optional[UUID] = None
    organization_id: Optional[UUID] = None
    # Resolves (or creates) an Organization by name and sets organization_id
    # from it — same convenience as registration_desk.py/public_registration.py.
    # A blank/whitespace-only value is a no-op, never a clear.
    organization_name: Optional[str] = None
    notes: Optional[str] = None


class ContactRelationshipCreate(BaseModel):
    related_contact_id: UUID
    relation: str  # guardian_of|child_of|sibling_of|spouse_of|other


class ContactRoleEventOut(BaseModel):
    """One row of a contact's role timeline (2026-07-24) — GET
    /spine/contacts/{id}/role-history. `role` is whatever vocabulary was
    actually mutated: a raw `users.roles` value (applicant, instructor, ...)
    for staff role edits, or a `contact_roles` value (student,
    parent_guardian, ...) for contact-only changes — see
    services/spine/role_history.py."""

    id: UUID
    role: str
    action: Literal["added", "removed"]
    # registration|desk|import|contact_edit|user_role_edit|user_created|backfill_initial
    source: str
    changed_by_user_id: Optional[UUID] = None
    changed_by_name: Optional[str] = None
    occurred_at: datetime

    class Config:
        from_attributes = True


# ── Organization ─────────────────────────────────────────────────────────

class OrganizationBase(BaseModel):
    name_latin: str
    name_arabic: Optional[str] = None
    org_type: str  # school|university|sponsor|government|ngo|company|other
    country: Optional[str] = None
    city: Optional[str] = None
    primary_contact_id: Optional[UUID] = None
    owner_user_id: Optional[UUID] = None
    notes: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationUpdate(BaseModel):
    name_latin: Optional[str] = None
    name_arabic: Optional[str] = None
    org_type: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    primary_contact_id: Optional[UUID] = None
    owner_user_id: Optional[UUID] = None
    notes: Optional[str] = None


class OrganizationOut(OrganizationBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


# ── Merge reviews ────────────────────────────────────────────────────────

class MergeReviewOut(BaseModel):
    id: UUID
    reason: str
    status: str
    detail: Optional[dict] = None
    created_at: datetime
    resolved_by: Optional[UUID] = None
    resolved_at: Optional[datetime] = None
    # Both candidates' summary info inlined so the frontend doesn't need a
    # second round-trip per row — plain fields only, no similarity hint.
    candidate_a: Optional[ContactBrief] = None
    candidate_b: Optional[ContactBrief] = None

    class Config:
        from_attributes = True


class MergeResolveRequest(BaseModel):
    action: Literal["merge", "keep_separate", "link_household"]
    # Required (and must be one of the review's two candidates) only for "merge".
    winner_id: Optional[UUID] = None
    # Required only for "link_household" — e.g. guardian_of/child_of/sibling_of/
    # spouse_of/other. Ignored for the other two actions.
    relation: Optional[str] = None

    @model_validator(mode="after")
    def _validate_action_fields(self) -> "MergeResolveRequest":
        if self.action == "merge" and self.winner_id is None:
            raise ValueError("winner_id is required when action is 'merge'")
        if self.action == "link_household" and not (self.relation or "").strip():
            raise ValueError("relation is required when action is 'link_household'")
        return self
