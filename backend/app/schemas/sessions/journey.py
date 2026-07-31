"""Materials, responsibilities and the payment bridge (I5-5 … I5-8)."""

from datetime import datetime
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
    payment_terms_note: str
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
    session_id: UUID
    session_date: str
    workshop_description: str
    role: str
    location: str | None = None
    duration_hours: float | None = None
    cohort_name: str | None = None


class BillSessionsIn(BaseModel):
    """Turn chosen completed sessions into payment lines. Amount is still
    typed by ops afterwards — nothing here invents money."""

    session_ids: list[UUID]
