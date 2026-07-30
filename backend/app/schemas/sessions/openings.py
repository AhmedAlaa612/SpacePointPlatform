"""Delivery roles, openings and add-ons (I5-3, I5-4, §G-addons)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ── delivery roles (I5-3) ───────────────────────────────────────────────────

class DeliveryRoleOut(BaseModel):
    id: UUID
    name: str
    sort_order: int
    is_active: bool

    class Config:
        from_attributes = True


class DeliveryRoleCreate(BaseModel):
    name: str
    # Omitted appends to the end. Sort order is seniority, lowest first.
    sort_order: int | None = None


class DeliveryRoleUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


# ── openings (I5-4) ─────────────────────────────────────────────────────────

class OpeningIn(BaseModel):
    role_id: UUID
    slots: int = Field(default=1, ge=1)
    amount_aed: Decimal | None = None
    notes: str | None = None


class SetOpeningsIn(BaseModel):
    """The full set for this session — the API takes the whole list, not a
    diff, so a client never has to reconcile and a half-applied edit can't
    leave a session advertising a role nobody wants."""

    openings: list[OpeningIn]


class OpeningOut(BaseModel):
    id: UUID
    session_id: UUID
    role_id: UUID
    role_name: str
    slots: int
    # None of these three are stored — all derived from assignments/interest.
    filled: int
    remaining: int
    waitlist: int
    amount_aed: Decimal | None = None
    notes: str | None = None


# ── add-ons (§G-addons) ─────────────────────────────────────────────────────

AddonSource = Literal["offer", "interest", "invite", "survey", "payment"]


class AddonIn(BaseModel):
    """`status` is deliberately absent: it is decided by `source`, since ops
    offering something has already agreed it and an instructor asking has
    not. Letting a caller set it would let a request arrive pre-approved."""

    description: str
    amount_aed: Decimal = Decimal("0")
    source: AddonSource = "offer"
    # NULL user = attached to the role, for whoever takes it.
    user_id: UUID | None = None
    role_id: UUID | None = None
    notes: str | None = None


class AddonDecisionIn(BaseModel):
    status: Literal["agreed", "declined"]


class AddonOut(BaseModel):
    id: UUID
    session_id: UUID
    user_id: UUID | None = None
    user_name: str | None = None
    role_id: UUID | None = None
    role_name: str | None = None
    description: str
    amount_aed: Decimal
    notes: str | None = None
    source: str
    status: str
    created_at: datetime | None = None
    decided_at: datetime | None = None
