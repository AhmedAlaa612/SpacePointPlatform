"""Schemas for the check-in scanner (V2 R2-5) — an operations staff member
scans a ticket's QR (or types the token manually) at the door of a specific
session. Kept in its own module, mirroring how this domain's other schema
modules are split (public_registration.py, registration_desk.py, cohorts.py)
rather than folded into one of those.
"""

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel


class CheckInRequest(BaseModel):
    token: str
    session_id: UUID


class CheckInResponse(BaseModel):
    """Everything the door-scanner UI needs to show a big pass/fail result
    card. check_in() (services/sessions/registration.py) only returns the
    AttendanceRecord itself, so the router resolves the student's name (via
    the registration this attendance record belongs to) plus the
    program/cohort name, for a friendlier confirmation than a bare id."""

    attendance_id: UUID
    att_status: str
    method: str
    recorded_at: datetime
    student_name: str
    program_name: str | None = None
    cohort_name: str | None = None


class TodaySessionOut(BaseModel):
    """One row for the scanner's "pick today's session" step — a Session
    joined with its cohort/program name so the picker can show something
    human-readable. Distinct from schemas/sessions/cohorts.py's SessionOut,
    which has no cohort/program name (that module's list endpoints are always
    already scoped to one cohort)."""

    id: UUID
    cohort_id: UUID
    cohort_name: str
    program_name: str
    meeting_date: date
    starts_at: time | None = None
    title: str | None = None
