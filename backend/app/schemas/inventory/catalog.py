"""Locations, the item catalogue, and kit templates (I1-3)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Categories are ops-editable data (`item_categories`), not a fixed set —
# `str` here, validated against that table at the router.
ItemCategory = str


# ── locations ───────────────────────────────────────────────────────────────

class LocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    country: str = Field(min_length=2, max_length=2, description="ISO-3166 alpha-2, e.g. AE")
    notes: str | None = None
    address: str | None = None
    maps_url: str | None = None


class LocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    is_active: bool | None = None
    notes: str | None = None
    address: str | None = None
    maps_url: str | None = None


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    country: str
    is_active: bool
    notes: str | None
    address: str | None = None
    maps_url: str | None = None
    created_at: datetime | None


# ── items ───────────────────────────────────────────────────────────────────

class ItemCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=32)


class ItemCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=32)
    sort_order: int | None = None


class ItemCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    sort_order: int


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    category: ItemCategory = "other"
    returnable_default: bool = False
    notes: str | None = None
    # Shown to an instructor picking from the equipment shelf (B3) — distinct
    # from `notes`, which is ops-facing.
    description: str | None = None
    # Sized/variant merchandise only — "T-Shirt" + "L". Both optional and
    # independent of each other at the schema level; the router blanks
    # `variant_label` if `variant_group` isn't set (a label means nothing
    # without a group to browse it under).
    variant_group: str | None = Field(default=None, max_length=128)
    variant_label: str | None = Field(default=None, max_length=32)


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    category: ItemCategory | None = None
    returnable_default: bool | None = None
    notes: str | None = None
    description: str | None = None
    variant_group: str | None = Field(default=None, max_length=128)
    variant_label: str | None = Field(default=None, max_length=32)


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str
    returnable_default: bool
    notes: str | None
    description: str | None
    variant_group: str | None = None
    variant_label: str | None = None
    # Resolved at read time from (image_bucket, image_path) — never the raw
    # columns, so a signed URL is never stale.
    image_url: str | None = None


# ── kit templates ───────────────────────────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=16, description="Label prefix, e.g. SATKIT")


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    code: str | None = Field(default=None, min_length=1, max_length=16)
    is_active: bool | None = None


class TemplateLineIn(BaseModel):
    item_id: uuid.UUID
    required_qty: int = Field(ge=1)


class TemplateLineOut(BaseModel):
    item_id: uuid.UUID
    item_name: str
    required_qty: int


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str
    is_active: bool


class TemplateDetailOut(TemplateOut):
    items: list[TemplateLineOut] = []
