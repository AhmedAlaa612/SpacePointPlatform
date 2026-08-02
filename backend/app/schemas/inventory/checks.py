"""The session loop (I2-1/I2-2)."""

import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, model_validator

CheckPhase = Literal["pre", "post", "adhoc"]


class KitSessionOut(BaseModel):
    """One session a kit has been earmarked for — past or future. The
    reverse of `SessionKitOut`, for a kit's own "everywhere I've been"
    calendar."""

    session_id: uuid.UUID
    cohort_id: uuid.UUID
    cohort_name: str
    program_name: str
    title: str
    meeting_date: date
    starts_at: time | None = None
    return_status: str | None = None
    received: bool
    ops_confirmed: bool


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
    pre_checked: bool = False
    post_checked: bool = False
    # No custody leg: these three are the instructor's own report and ops's
    # review of it — not a movement, not a holder.
    received: bool = False
    received_at: datetime | None = None
    return_status: Literal["returned", "return_later"] | None = None
    returned_at: datetime | None = None
    ops_confirmed: bool = False
    # Cohort-level kit defaults (Phase 3 follow-up): True when this kit came
    # from the cohort's default list rather than this session's own
    # `SessionKit` rows — mirrors `SessionKitStatusOut.level`.
    inherited: bool = False


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
    # session|cohort|none — mirrors `SessionMaterialsOut.level` in
    # `schemas/sessions/journey.py`. "session" once this session has had its
    # own kit activity (even if that activity emptied it out), "cohort" while
    # it is still inheriting the cohort's default, "none" if neither has any.
    level: str = "none"


class ReceiveKitsIn(BaseModel):
    """The instructor confirming they have these kits — per kit, or all of
    them at once."""

    kit_ids: list[uuid.UUID]


class MarkKitsReturnedIn(BaseModel):
    """The instructor reporting kits back, or saying they're coming back
    later. No destination — where it lands is ops's call, made separately."""

    kit_ids: list[uuid.UUID]
    later: bool = False
    note: str | None = None


class ConfirmKitReturnsIn(BaseModel):
    """Ops reviewing the instructor's report, in the session review screen.
    Restocking is optional and separate from confirming the report itself."""

    kit_ids: list[uuid.UUID]
    restock_warehouse_id: uuid.UUID | None = None


# ── cohort-level kit defaults (Phase 3 follow-up) ───────────────────────────
# `AssignKitsIn` above is reused as the request body for setting a cohort's
# default kit list — same "full resubmit" contract, one level up.

class CohortKitOut(BaseModel):
    kit_id: uuid.UUID
    label: str
    template_name: str
    location_name: str


class CohortKitStatusOut(BaseModel):
    """A cohort's default kit list, for the ops-facing cohort settings
    screen."""

    kits: list[CohortKitOut]
