"""Merchandise (I2-4). Kits have no equivalent schema here — see
schemas/inventory/checks.py for how a session's kits are received and
returned."""

import uuid
from datetime import date

from pydantic import BaseModel, Field


class IssueMerchIn(BaseModel):
    item_id: uuid.UUID
    to_user_id: uuid.UUID
    from_warehouse_id: uuid.UUID
    qty: int = Field(default=1, ge=1)
    # None means "use the item's own default" — vests yes, T-shirts no.
    returnable: bool | None = None
    due_back_on: date | None = None
    note: str | None = None


class ReturnMerchIn(BaseModel):
    item_id: uuid.UUID
    from_user_id: uuid.UUID
    to_warehouse_id: uuid.UUID
    qty: int = Field(default=1, ge=1)


class HeldItemOut(BaseModel):
    item_id: uuid.UUID
    item_name: str
    variant_group: str | None = None
    variant_label: str | None = None
    qty: int
    due_back_on: date | None = None
