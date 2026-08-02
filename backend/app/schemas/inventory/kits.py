"""Kits, stock and movements (I1-3)."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

KitStatus = Literal["working", "damaged", "retired", "lost"]
MovementReason = Literal[
    "issue", "return", "transfer", "refill", "receive", "writeoff", "adjust", "sold"
]


# ── kits ────────────────────────────────────────────────────────────────────

class KitCreate(BaseModel):
    template_id: uuid.UUID
    label: str = Field(min_length=1, max_length=32, description="e.g. SP-SATKIT-0001")
    current_warehouse_id: uuid.UUID
    notes: str | None = None
    complete: bool = Field(
        default=False,
        description="Seed contents from the template's required quantities via `receive` movements.",
    )


class KitBulkCreate(BaseModel):
    """Create N kits of one template in one warehouse, complete from the BOM.

    The first-day path: without it, entering an existing fleet means N × a
    28-field form, which stalls halfway. Labels are generated from the
    template code and the highest existing number.
    """

    template_id: uuid.UUID
    warehouse_id: uuid.UUID
    count: int = Field(ge=1, le=200)
    complete: bool = Field(
        default=True,
        description="Fill each kit to its template quantities. False creates them empty.",
    )


class KitUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=32)
    status: KitStatus | None = None
    notes: str | None = None


class KitShortageOut(BaseModel):
    item_id: uuid.UUID
    item_name: str
    required: int
    actual: int
    short_by: int


class KitContentOut(BaseModel):
    item_id: uuid.UUID
    item_name: str
    qty: int


class KitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    template_id: uuid.UUID
    label: str
    status: str
    current_location_id: uuid.UUID
    current_warehouse_id: uuid.UUID
    current_holder_user_id: uuid.UUID | None
    notes: str | None


class KitListItem(KitOut):
    """List view. `shortage_count` drives the completeness badge and is
    computed in one query for the whole page, never per row."""

    template_code: str
    location_name: str
    warehouse_name: str
    holder_name: str | None = None
    shortage_count: int = 0


class KitDetailOut(KitOut):
    template_code: str
    template_name: str
    location_name: str
    warehouse_name: str
    holder_name: str | None = None
    public_token: str
    contents: list[KitContentOut] = []
    shortages: list[KitShortageOut] = []


# ── movements ───────────────────────────────────────────────────────────────

class KitMoveIn(BaseModel):
    """Move one kit. Destination is a warehouse (back on a shelf) or a person
    (out with an instructor) — never both."""

    to_warehouse_id: uuid.UUID | None = None
    to_user_id: uuid.UUID | None = None
    reason: MovementReason = "transfer"
    session_id: uuid.UUID | None = None
    due_back_on: date | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _one_destination(self):
        if (self.to_warehouse_id is None) == (self.to_user_id is None):
            raise ValueError("Give exactly one destination: a warehouse or a person")
        return self


class StockMoveIn(BaseModel):
    """Move a quantity of one item. Either side may be a warehouse or a kit;
    a refill is from_warehouse_id + to_kit_id."""

    item_id: uuid.UUID
    qty: int = Field(ge=1)
    from_warehouse_id: uuid.UUID | None = None
    from_kit_id: uuid.UUID | None = None
    to_warehouse_id: uuid.UUID | None = None
    to_user_id: uuid.UUID | None = None
    to_kit_id: uuid.UUID | None = None
    reason: MovementReason = "transfer"
    due_back_on: date | None = None
    note: str | None = None


class StockAdjustIn(BaseModel):
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    new_qty: int = Field(ge=0, description="The counted total, not a delta")
    reason: str = Field(min_length=1, description="Mandatory — an unexplained change is the one you'll want explained")


class StockAdjustLine(BaseModel):
    item_id: uuid.UUID
    warehouse_id: uuid.UUID
    new_qty: int = Field(ge=0, description="The counted total, not a delta")


class StockAdjustBulkIn(BaseModel):
    """One stocktake, many item/warehouse counts, one reason for all of them."""

    reason: str = Field(min_length=1)
    levels: list[StockAdjustLine]


class KitCountLine(BaseModel):
    item_id: uuid.UUID
    new_qty: int = Field(ge=0, description="The counted total, not a delta")


class KitCountIn(BaseModel):
    """Set a kit's contents to a counted total, per item.

    `from_shelf` decides where the difference comes from/goes: ticked moves
    stock between the kit and its own warehouse (refill / put-back); unticked
    treats it as arriving from nowhere in particular (receive) or leaving for
    no shelf in particular (a loss/correction) — see `count_kit()`.
    """

    reason: str = Field(min_length=1)
    from_shelf: bool = False
    lines: list[KitCountLine]


class StockLevelOut(BaseModel):
    item_id: uuid.UUID
    item_name: str
    category: str | None = None
    location_id: uuid.UUID
    location_name: str
    warehouse_id: uuid.UUID
    warehouse_name: str
    qty: int


class MovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kit_id: uuid.UUID | None
    item_id: uuid.UUID | None
    qty: int | None
    from_location_id: uuid.UUID | None
    from_warehouse_id: uuid.UUID | None
    from_user_id: uuid.UUID | None
    from_kit_id: uuid.UUID | None
    to_location_id: uuid.UUID | None
    to_warehouse_id: uuid.UUID | None
    to_user_id: uuid.UUID | None
    to_kit_id: uuid.UUID | None
    session_id: uuid.UUID | None
    reason: str
    due_back_on: date | None
    note: str | None
    created_by: uuid.UUID
    created_at: datetime | None
    confirmed_by: uuid.UUID | None
    confirmed_at: datetime | None
    from_location_name: str | None = None
    from_warehouse_name: str | None = None
    from_user_name: str | None = None
    to_location_name: str | None = None
    to_warehouse_name: str | None = None
    to_user_name: str | None = None


class PublicKitOut(BaseModel):
    """What an unauthenticated scan reveals. Deliberately no location, no
    holder and no contents — a QR on a box that leaves the building is
    readable by whoever picks it up."""

    label: str
    template_name: str
    status: str
    owner: str
    contact_email: str


class HolderOut(BaseModel):
    """Someone a kit can be handed to."""

    id: uuid.UUID
    full_name: str
    roles: list[str]


class MyKitOut(BaseModel):
    """What an instructor sees for a kit they are holding."""

    id: uuid.UUID
    label: str
    template_name: str
    status: str
    location_name: str
    due_back_on: date | None = None
    shortage_count: int = 0
    # Where "mark returned" defaults to — the session it was last issued for,
    # if there was one. Null only when that can't be resolved either.
    default_return_warehouse_id: uuid.UUID | None = None
    default_return_warehouse_name: str | None = None
