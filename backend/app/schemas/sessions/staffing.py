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
    # This instructor's own day record for this session (2026-08-28) — None
    # when they haven't checked in yet (no InstructorSessionDay row exists),
    # which the "My Sessions" redesign treats the same as day_status="draft".
    att_status: str | None = None
    checked_in_at: datetime | None = None
    day_status: str | None = None


# ── Cohort-level staffing (2026-08-24) ──────────────────────────────────────
# The cohort layer over the session-scoped marketplace above: ops opens one
# call across N sessions, the instructor answers it once with a role and the
# days they can do, and ops picks from one table instead of N.

class CohortCallSessionOut(BaseModel):
    """One tickable day inside a cohort card."""
    session_id: UUID
    title: str | None = None
    meeting_date: date
    starts_at: time | None = None
    # Whether this instructor has already ticked it — lets the card come back
    # showing their previous answer instead of a blank form.
    selected: bool = False


class AvailableCohortCallOut(BaseModel):
    """One cohort card on the instructor's Available Sessions page.

    `openings` are summed across the call's sessions, so "1 of 3 left" is a
    cohort-scale statement rather than one session's. `amount_aed` on each is
    the per-session rate resolved through the full hierarchy (session opening
    -> cohort opening -> role default).
    """
    cohort_call_id: UUID
    cohort_id: UUID
    cohort_name: str
    program_name: str
    program_type: str | None = None
    description: str | None = None
    label: str | None = None
    starts_on: date
    ends_on: date
    session_count: int
    location: str | None = None
    location_address: str | None = None
    location_map_url: str | None = None
    interested_count: int
    sessions: list[CohortCallSessionOut] = []
    openings: list[OpeningSummary] = []

    my_interest: bool = False
    my_role_id: UUID | None = None
    my_note: str | None = None
    my_needs_transport: bool = False
    my_needs_ops_support: bool = False
    my_travelling_from_other_city: bool = False
    my_concerns: str | None = None


class AvailableWorkOut(BaseModel):
    """Everything an instructor can apply for right now.

    Deliberately two lists rather than one flattened feed: a cohort call is a
    single decision about a run of days, while a session opened on its own is
    still a standalone offer. `single_sessions` reuses `AvailableSessionOut`
    unchanged, so the existing `GET /sessions/available` contract keeps
    working for one release instead of shifting under the current page.
    """
    cohort_calls: list[AvailableCohortCallOut] = []
    single_sessions: list[AvailableSessionOut] = []


class RegisterCohortInterestRequest(BaseModel):
    # The days they can actually do. Anything not offered by this call is
    # ignored rather than erroring — the client's list can lag a call edit.
    session_ids: list[UUID]
    role_id: UUID | None = None
    note: str | None = None
    # Operations process doc §2.
    needs_transport: bool = False
    needs_ops_support: bool = False
    travelling_from_other_city: bool = False
    concerns: str | None = None
    # The version of the combined role + general responsibilities text that
    # was on screen. A stale one is refused, same as the per-session flow.
    responsibilities_version: str | None = None


class CohortCallInterestOut(BaseModel):
    """One row of the ops applicant table — one instructor, not one session."""
    user_id: UUID
    full_name: str
    email: str
    role_id: UUID | None = None
    role_name: str | None = None
    session_ids: list[UUID] = []
    session_count: int
    note: str | None = None
    needs_transport: bool = False
    needs_ops_support: bool = False
    travelling_from_other_city: bool = False
    concerns: str | None = None
    responsibilities_accepted_at: datetime | None = None
    # Whether the cohort's city is one they already said they'd travel to
    # (ApplicantProfile.deliver_city_ids) — same signal the per-session
    # eligible-instructors list surfaces.
    available_in_city: bool = False
    status: str
    already_assigned: bool = False
    created_at: datetime | None = None


class SelectForCohortRequest(BaseModel):
    user_ids: list[UUID]
    # Omitted uses whichever role each applicant applied for, then the most
    # senior — picking somebody as what they asked to be shouldn't require
    # restating it.
    role_id: UUID | None = None
    # Omitted assigns exactly the days each applicant ticked.
    session_ids: list[UUID] | None = None
    cohort_call_id: UUID | None = None
    close_call: bool = True
    rate_basis: Literal["per_session", "flat"] = "per_session"
    flat_amount_aed: float | None = None


class CohortSelectionOut(BaseModel):
    user_id: UUID
    role_id: UUID
    session_ids: list[UUID]
    rate_aed: float | None = None
    rate_basis: str
    flat_amount_aed: float | None = None


class CohortAssignmentOut(BaseModel):
    """Who is staffed on a cohort, in what role, at what agreed rate."""
    id: UUID
    cohort_id: UUID
    user_id: UUID
    full_name: str
    email: str
    role_id: UUID
    role_name: str
    rate_basis: str
    rate_aed: float | None = None
    flat_amount_aed: float | None = None
    status: str
    source: str
    session_count: int
    created_at: datetime | None = None
