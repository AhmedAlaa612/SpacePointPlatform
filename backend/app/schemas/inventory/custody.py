"""Handover and merchandise (I2-3/I2-4)."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class IssueSessionKitsIn(BaseModel):
    """`to_user_id` omitted means the session's lead instructor, which is the
    answer almost every time."""

    to_user_id: uuid.UUID | None = None
    due_back_on: date | None = None


class ReturnSessionKitsIn(BaseModel):
    """A destination is required. "Returned" without saying where leaves the
    register claiming a kit is on a shelf without saying which one."""

    to_location_id: uuid.UUID


class IssueMerchIn(BaseModel):
    item_id: uuid.UUID
    to_user_id: uuid.UUID
    from_location_id: uuid.UUID
    qty: int = Field(default=1, ge=1)
    # None means "use the item's own default" — vests yes, T-shirts no.
    returnable: bool | None = None
    due_back_on: date | None = None
    note: str | None = None


class ReturnMerchIn(BaseModel):
    item_id: uuid.UUID
    from_user_id: uuid.UUID
    to_location_id: uuid.UUID
    qty: int = Field(default=1, ge=1)


class HeldItemOut(BaseModel):
    item_id: uuid.UUID
    item_name: str
    qty: int
    due_back_on: date | None = None


class UnconfirmedHandoverOut(BaseModel):
    movement_id: uuid.UUID
    kit_id: uuid.UUID | None
    item_id: uuid.UUID | None
    qty: int | None
    to_user_id: uuid.UUID | None
    to_user_name: str | None
    due_back_on: date | None
    created_at: datetime | None
