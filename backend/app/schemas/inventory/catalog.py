"""Locations, the item catalogue, and kit templates (I1-3)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ItemCategory = Literal["sensor", "board", "tool", "mechanical", "merch", "other"]


# ── locations ───────────────────────────────────────────────────────────────

class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    country: str = Field(min_length=2, max_length=2, description="ISO-3166 alpha-2, e.g. AE")
    notes: str | None = None


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    is_active: bool | None = None
    notes: str | None = None


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    country: str
    is_active: bool
    notes: str | None
    created_at: datetime | None


# ── items ───────────────────────────────────────────────────────────────────

class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    category: ItemCategory = "other"
    is_consumable: bool = False
    returnable_default: bool = False
    notes: str | None = None
    # Shown to an instructor picking from the equipment shelf (B3) — distinct
    # from `notes`, which is ops-facing.
    description: str | None = None


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    category: ItemCategory | None = None
    is_consumable: bool | None = None
    returnable_default: bool | None = None
    notes: str | None = None
    description: str | None = None


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str
    is_consumable: bool
    returnable_default: bool
    notes: str | None
    description: str | None


# ── kit templates ───────────────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=16, description="Label prefix, e.g. SATKIT")


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    is_active: bool | None = None


class TemplateLineIn(BaseModel):
    item_id: uuid.UUID
    required_qty: int = Field(ge=1)


class TemplateLineOut(BaseModel):
    item_id: uuid.UUID
    item_name: str
    required_qty: int
    is_consumable: bool


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    is_active: bool


class TemplateDetailOut(TemplateOut):
    items: list[TemplateLineOut] = []
