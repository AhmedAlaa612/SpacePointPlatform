"""Materials, responsibilities and the payment bridge (I5-5 … I5-8)."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel


# ── materials (I5-6) ────────────────────────────────────────────────────────

class MaterialOut(BaseModel):
    id: UUID
    program_id: UUID | None = None
    cohort_id: UUID | None = None
    session_id: UUID | None = None
    title: str
    notes: str | None = None
    # Resolved: a signed link for stored files, the raw one for external links.
    url: str | None = None
    filename: str | None = None
    sort_order: int = 1
    created_at: datetime | None = None


class SessionMaterialsOut(BaseModel):
    """What an instructor sees for a session, plus where it came from — so ops
    can tell "inherited from the program" apart from "this session has none"."""

    level: str          # program|cohort|session|none
    materials: list[MaterialOut]


class MaterialLinkIn(BaseModel):
    title: str
    url: str
    notes: str | None = None


# ── responsibilities (I5-5) ─────────────────────────────────────────────────

class ResponsibilitiesOut(BaseModel):
    text: str
    # Hash of the text, not a counter — it changes exactly when the words do.
    version: str
    # Set when a role_id was requested and it resolved to a real role — lets
    # the UI label the block "Responsibilities — Lead Facilitator" instead of
    # a generic heading.
    role_name: str | None = None


class ResponsibilitiesIn(BaseModel):
    text: str


class AcceptResponsibilitiesIn(BaseModel):
    """The version that was on screen. A stale one is refused rather than
    silently accepted — otherwise someone agrees to text they never saw."""

    version: str


# ── payment bridge (I5-8) ───────────────────────────────────────────────────

class UnbilledSessionOut(BaseModel):
    """One draft payment line for work this instructor hasn't been paid for.

    Since 2026-08-24 a line is normally a whole *cohort* — `cohort_id` set,
    `session_id` null, `session_count`/`rate_aed` filled, and `session_date`
    holding the cohort's date range rather than one date. A session delivered
    outside any cohort assignment still produces the original one-row-per-
    session shape, with `session_id` set and `cohort_id` null.

    `line_id` is what the client sends back to bill it: the cohort id for a
    cohort line, the session id for a single one. Callers should use it rather
    than reconstructing the distinction themselves.
    """

    # Exactly one of these two is set; `line_id` is whichever it is.
    cohort_id: UUID | None = None
    session_id: UUID | None = None
    line_id: UUID
    # Every session this line pays for — one entry for a single-session line.
    session_ids: list[UUID] = []
    session_date: str
    workshop_description: str
    role: str
    location: str | None = None
    duration_hours: float | None = None
    cohort_name: str | None = None
    session_count: int = 1
    rate_aed: float | None = None
    # Pre-computed from the agreed rate x approved days. Still a draft: ops
    # edits it on the letter before publishing.
    compensation_aed: float = 0.0
    rate_basis: str = "per_session"


class BillSessionsIn(BaseModel):
    """Turn chosen billable lines into payment lines.

    `line_ids` are `UnbilledSessionOut.line_id` values — a cohort id for a
    cohort line, a session id for a single one. The amount arrives
    pre-computed from the rate agreed at staffing time and stays editable on
    the letter until it is published, so ops still decides the money; they
    just no longer type a number the system already knows.
    """

    line_ids: list[UUID]


class PendingPaymentInstructorOut(BaseModel):
    """One row of the admin's payment-letter to-do list: an instructor with
    completed sessions not yet on any of their payment letters."""

    instructor_user_id: UUID
    full_name: str
    email: str
    # How many letter rows this would produce — normally one per cohort.
    pending_cohort_count: int = 0
    # The days behind those rows.
    pending_session_count: int
    earliest_date: date
    latest_date: date
