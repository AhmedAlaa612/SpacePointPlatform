"""Schemas for the staffing marketplace (V2 W4, S4-1/S4-2). Session-scoped —
see services/sessions/staffing.py's module docstring for why.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.sessions.cohorts import StaffingStatus


class RegisterInterestRequest(BaseModel):
    note: str | None = None


class InterestOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    note: str | None = None
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


class SelectInstructorsRequest(BaseModel):
    user_ids: list[UUID]
    role: Literal["lead", "co"] = "lead"


class SelectInstructorsResponse(BaseModel):
    assigned: list[UUID]
    # Selected without ever registering interest — an allowed ops override,
    # surfaced here rather than silently hidden (mandatory per S4-1's spec).
    without_interest: list[UUID]


class AvailableSessionOut(BaseModel):
    """S4-3 "Available sessions" instructor page — one open-call session."""
    session_id: UUID
    cohort_id: UUID
    cohort_name: str
    program_name: str
    location: str | None = None
    meeting_date: date
    starts_at: time | None = None
    interested_count: int
    my_interest: bool
    my_note: str | None = None


class MySessionOut(BaseModel):
    """S4-3 "My sessions" instructor page — one session this user is assigned to."""
    session_id: UUID
    cohort_id: UUID
    cohort_name: str
    program_name: str
    location: str | None = None
    meeting_date: date
    starts_at: time | None = None
    my_role: Literal["lead", "co"]
    staffing_status: StaffingStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
