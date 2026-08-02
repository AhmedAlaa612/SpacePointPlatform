"""Self-serve holdings — what one person currently has, and giving it back
themselves (2026-08-01)."""

import uuid
from datetime import date

from pydantic import BaseModel


class ReturnOwnKitIn(BaseModel):
    """Omitted destination resolves to the session it was last issued for,
    if there was one — see `holdings.default_kit_return_warehouse`."""

    to_warehouse_id: uuid.UUID | None = None
    note: str | None = None


class ReturnOwnItemIn(BaseModel):
    qty: int = 1
    to_warehouse_id: uuid.UUID | None = None
    note: str | None = None


class MyHeldItemOut(BaseModel):
    """A bulk item — equipment or merch — this person is currently holding."""

    item_id: uuid.UUID
    item_name: str
    variant_group: str | None = None
    variant_label: str | None = None
    qty: int
    due_back_on: date | None = None
    default_warehouse_id: uuid.UUID | None = None
    default_warehouse_name: str | None = None
