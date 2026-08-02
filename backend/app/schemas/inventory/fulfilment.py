"""The storekeeper fulfilment queue (I3-1)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ShortageLineOut(BaseModel):
    item_id: uuid.UUID
    item_name: str
    required: int
    actual: int
    short_by: int
    # How many are on the shelf in the kit's own warehouse. This is what makes
    # the queue actionable rather than merely informative.
    available: int


class FulfilmentKitOut(BaseModel):
    kit_id: uuid.UUID
    label: str
    template_name: str
    status: str
    location_id: uuid.UUID
    location_name: str
    warehouse_id: uuid.UUID
    warehouse_name: str
    out_with_someone: bool
    # Set = a storekeeper looked and the shelf was empty. Null = nobody has
    # been to it yet. The difference is the only thing this queue stores.
    awaiting_parts_since: datetime | None = None
    awaiting_parts_note: str | None = None
    shortages: list[ShortageLineOut]
    fixable_now: int


class FulfilLineIn(BaseModel):
    item_id: uuid.UUID
    qty: int = Field(ge=1)


class FulfilKitIn(BaseModel):
    """`from_warehouse_id` omitted means the kit's own warehouse — parts come
    off the shelf the box is sitting on, which is the case needing no thought."""

    lines: list[FulfilLineIn]
    from_warehouse_id: uuid.UUID | None = None


class AwaitingPartsIn(BaseModel):
    awaiting: bool
    note: str | None = None
