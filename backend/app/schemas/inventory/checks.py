"""The session loop (I2-1/I2-2)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, model_validator

CheckPhase = Literal["pre", "post", "adhoc"]


class AssignKitsIn(BaseModel):
    """The full set of kits for this session — the UI is a multi-select that
    resubmits everything, so assigning is idempotent rather than a 409."""

    kit_ids: list[uuid.UUID]


class ExpectedCountOut(BaseModel):
    """One line of the check form, prefilled with what we currently believe is
    in the box. Prefilled rather than blank so the common case is one tap; a
    form demanding 27 numbers gets 27 guesses."""

    item_id: uuid.UUID
    item_name: str
    required: int
    expected: int


class SessionKitOut(BaseModel):
    kit_id: uuid.UUID
    label: str
    template_name: str
    status: str
    location_name: str
    holder_name: str | None = None
    pre_checked: bool = False
    post_checked: bool = False


class CheckSubmitIn(BaseModel):
    """Either real counts, or an explicit skip.

    Skipping is a first-class outcome, not the absence of a submission — a
    later shortage needs to know whether anyone looked in the box beforehand.
    """

    phase: CheckPhase
    counts: dict[uuid.UUID, int] = {}
    skipped: bool = False
    note: str | None = None

    @model_validator(mode="after")
    def _counts_or_skip(self):
        if self.skipped and self.counts:
            raise ValueError("A skipped check has no counts")
        if not self.skipped and not self.counts:
            raise ValueError("Count something, or mark the check skipped")
        return self


class CheckOut(BaseModel):
    id: uuid.UUID
    kit_id: uuid.UUID
    session_id: uuid.UUID | None
    phase: str
    skipped: bool
    checked_by: uuid.UUID
    checked_by_name: str | None = None
    counts: dict[str, int]
    missing: dict[str, int]
    note: str | None
    created_at: datetime | None


class SessionKitStatusOut(BaseModel):
    """What the instructor's session page shows, and what gates finishing."""

    kits: list[SessionKitOut]
    outstanding_post_checks: list[uuid.UUID]
    can_finish: bool
    # B4: whether the viewing instructor has kits issued to them with an
    # unconfirmed custody movement — the one thing "I have them" actually
    # changes. False (rather than omitted) for the ops-side assign/unassign
    # calls, which have no instructor viewpoint to compute this against.
    pending_confirmation: bool = False
