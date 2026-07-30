"""Non-kit equipment taken to a session (I2-7)."""

import uuid

from pydantic import BaseModel, Field


class EquipmentLineIn(BaseModel):
    item_id: uuid.UUID
    qty: int = Field(default=1, ge=1)


class TakeEquipmentIn(BaseModel):
    """`location_id` omitted means "derive it from the assigned kits", which is
    the normal case — the kits have already been moved to the session's
    warehouse, so that is where the instructor is standing. It is only sent on
    the uncommon path where there is nothing to derive from."""

    lines: list[EquipmentLineIn]
    location_id: uuid.UUID | None = None
    note: str | None = None


class ReturnEquipmentIn(BaseModel):
    """Omitting a line is how "returning later" is expressed — it stays
    outstanding rather than being recorded as something it isn't."""

    lines: list[EquipmentLineIn]
    to_location_id: uuid.UUID | None = None


class EquipmentSearchOut(BaseModel):
    item_id: uuid.UUID
    item_name: str
    category: str
    available: int
    returnable: bool


class TakenEquipmentOut(BaseModel):
    item_id: uuid.UUID
    item_name: str
    qty_taken: int
    qty_returned: int
    outstanding: int
    returnable: bool


class SessionEquipmentOut(BaseModel):
    """What the equipment section renders.

    `location_id` is null when we can't derive a collection point — no kits
    assigned, or kits in more than one place — and that is the only time the
    UI shows a location dropdown at all.
    """

    location_id: uuid.UUID | None
    location_name: str | None
    lines: list[TakenEquipmentOut]
    outstanding_count: int
