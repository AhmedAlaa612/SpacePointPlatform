"""Schemas for the staffing marketplace (V2 W4, S4-1/S4-2). Session-scoped —
see services/sessions/staffing.py's module docstring for why.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.sessions.cohorts import BulkActionError, StaffingStatus


class RegisterInterestRequest(BaseModel):
    note: str | None = None
    # B1: which opening they're applying for. None is still valid — a
    # session with no configured openings, or an instructor who just wants
    # to flag interest generally.
    role_id: UUID | None = None


class InterestOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    note: str | None = None
    role_id: UUID | None = None
    role_name: str | None = None
    created_at: datetime


class EligibleInstructorOut(BaseModel):
    """Full instructor|facilitator roster for the ops select screen — not
    just whoever registered interest (operator requirement 2026-07-24)."""
    user_id: UUID
    full_name: str
    email: str
    photo_url: str | None = None
    interested: bool
    note: str | None = None
    # B1: what they actually applied for, so ops assigns by what was asked
    # rather than guessing.
    interest_role_id: UUID | None = None
    interest_role_name: str | None = None
    # 2026-08-08: did this instructor mark the session's resolved city
    # (session.location_id, else its cohort's) as somewhere they're open to
    # work? Always False if the session has no resolvable location/city.
    available_in_city: bool = False


class SelectInstructorsRequest(BaseModel):
    user_ids: list[UUID]
    role_id: UUID | None = None
    # False keeps the session at open_call so more instructors can still
    # register interest while ops picks people one at a time.
    close_call: bool = True


class SelectInstructorsResponse(BaseModel):
    assigned: list[UUID]
    # Selected without ever registering interest — an allowed ops override,
    # surfaced here rather than silently hidden (mandatory per S4-1's spec).
    without_interest: list[UUID]


class SessionCallOut(BaseModel):
    """One call on a session (2026-08-01) — a session can have several at
    once, each independently viewable/editable/closeable. Empty
    target_user_ids means public (open to every instructor/facilitator)."""
    id: UUID
    session_id: UUID
    status: Literal["open", "closed"]
    label: str | None = None
    target_user_ids: list[UUID] = []
    created_at: datetime | None = None
    closed_at: datetime | None = None


class CohortCallSessionOut(BaseModel):
    """One session grouped under a CohortCall — its own SessionCall status
    (open|closed) alongside the session's overall staffing_status, since a
    session can reach `staffed` (closing its call) while other sessions
    under the same cohort call are still open."""
    session_id: UUID
    meeting_date: date
    starts_at: time | None = None
    status: Literal["open", "closed"]  # this session's own SessionCall row
    staffing_status: StaffingStatus


class CohortCallOut(BaseModel):
    """A standing call grouping a chosen subset of a cohort's sessions
    (2026-08-01) — `status` is derived (open while any grouped session's
    call is still open) same as SessionCallOut.status is for a single call."""
    id: UUID
    cohort_id: UUID
    status: Literal["open", "closed"]
    label: str | None = None
    target_user_ids: list[UUID] = []
    sessions: list[CohortCallSessionOut] = []
    created_at: datetime | None = None
    closed_at: datetime | None = None


class OpenCohortCallRequest(BaseModel):
    # None = every currently-unstaffed session in the cohort (same default
    # open_call_for_cohort already uses). Given, restricts the call to just
    # those sessions — anything not actually in this cohort is reported back
    # in the response's `failed` list rather than erroring the whole batch.
    session_ids: list[UUID] | None = None
    user_ids: list[UUID] | None = None
    role_ids: list[UUID] | None = None
    label: str | None = None


class OpenCohortCallResponse(BaseModel):
    call: CohortCallOut
    # Reuses BulkActionResult's per-item error shape (schemas/sessions/
    # cohorts.py) rather than inventing a new one — same partial-failure
    # contract as bulk-open-call/bulk-assign-instructor.
    failed: list[BulkActionError] = []


class CloseCohortCallRequest(BaseModel):
    # None = close every still-open session grouped under this call.
    session_ids: list[UUID] | None = None
    clear_interest: bool = False


class AvailableSessionOut(BaseModel):
    """S4-3 "Available sessions" instructor page — one open-call session."""
    session_id: UUID
    cohort_id: UUID
    cohort_name: str
    program_name: str
    # What the session actually is ("Intro to Orbits"). Program + cohort alone
    # don't tell an instructor what they'd be teaching on the day.
    title: str | None = None
    location: str | None = None
    meeting_date: date
    starts_at: time | None = None
    interested_count: int
    my_interest: bool
    my_note: str | None = None

    # I5-5 — everything below is what an instructor needs to decide, and none
    # of it reached them before: they got a cohort name, a date and a place.
    program_type: str | None = None
    description: str | None = None
    # Full resolved location (2026-08-08) — the card shows name + address and
    # links out to the map, instead of a bare name.
    location_address: str | None = None
    location_map_url: str | None = None
    duration_hours: float | None = None
    # Per role: what is on offer, how many slots, how many are left.
    openings: list["OpeningSummary"] = []
    # Add-ons attached to the offer (not yet to a person).
    addons: list["AddonSummary"] = []
    # Whether this person has already ticked read-and-agree for this session.
    responsibilities_accepted: bool = False


class OpeningSummary(BaseModel):
    role_id: UUID
    role_name: str
    role_description: str | None = None
    slots: int
    remaining: int
    amount_aed: float | None = None
    notes: str | None = None


class AddonSummary(BaseModel):
    description: str
    amount_aed: float
    notes: str | None = None


class MySessionOut(BaseModel):
    """S4-3 "My sessions" instructor page — one session this user is assigned to."""
    session_id: UUID
    cohort_id: UUID
    cohort_name: str
    program_name: str
    title: str | None = None
    location: str | None = None
    # Full resolved location (2026-08-08) — the card shows name + address and
    # links out to the map, instead of a bare name.
    location_address: str | None = None
    location_maps_url: str | None = None
    meeting_date: date
    starts_at: time | None = None
    my_role: str
    staffing_status: StaffingStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
