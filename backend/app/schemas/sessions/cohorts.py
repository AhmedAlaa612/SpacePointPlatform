"""Pydantic schemas for the Cohort and Session models (V2 R2-3 — registration
desk). Mirrors app/models/sessions/cohort.py and session.py field-for-field.
"""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

# planned|registration_open|running|completed|cancelled — see the Cohort
# model's own comment for the authoritative list.
CohortStatus = Literal["planned", "registration_open", "running", "completed", "cancelled"]
StaffingStatus = Literal["unstaffed", "open_call", "staffed"]
Visibility = Literal["public", "private"]


class CohortBase(BaseModel):
    name: str
    starts_on: date | None = None
    ends_on: date | None = None
    location: str | None = None
    capacity: int | None = None
    lead_instructor_user_id: UUID | None = None
    madar_invitation_batch: str | None = None
    notes: str | None = None
    organization_id: UUID | None = None
    visibility: Visibility = "public"


class CohortCreate(CohortBase):
    program_id: UUID
    status: CohortStatus = "planned"


class CohortUpdate(BaseModel):
    name: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    location: str | None = None
    capacity: int | None = None
    lead_instructor_user_id: UUID | None = None
    status: CohortStatus | None = None
    madar_invitation_batch: str | None = None
    notes: str | None = None
    organization_id: UUID | None = None
    visibility: Visibility | None = None


class CohortOut(CohortBase):
    id: UUID
    program_id: UUID
    status: CohortStatus
    created_at: datetime
    # Convenience join populated only by the list endpoint (not a stored
    # field) — None everywhere else. Keeps the registrations/detail views
    # from needing a second request just to show which program a cohort
    # belongs to.
    program_name: str | None = None
    program_code: str | None = None

    class Config:
        from_attributes = True


class GenerateSessionsRequest(BaseModel):
    # One or more weekdays that repeat every week — e.g. [1, 3] for a
    # Tuesday+Thursday course. 0=Monday .. 6=Sunday, matching Python's
    # date.weekday(). `count` is the number of WEEKS to generate over, so
    # weekdays=[1, 3], count=6 produces 12 sessions (Tue+Thu x 6 weeks).
    weekdays: list[int]
    count: int
    starts_at: time | None = None


class SessionInstructorOut(BaseModel):
    user_id: UUID
    full_name: str
    role: str

    class Config:
        from_attributes = True


class SessionOut(BaseModel):
    id: UUID
    cohort_id: UUID
    meeting_date: date
    starts_at: time | None = None
    title: str | None = None
    material_url: str | None = None
    price: Decimal | None = None
    staffing_status: StaffingStatus
    created_at: datetime
    # Populated only by the list endpoint — the instructor(s) assigned to
    # this specific session (see SessionInstructor).
    instructors: list[SessionInstructorOut] = []
    interested_count: int = 0
    # Instructors this open call is restricted to. Empty means unrestricted —
    # visible to every instructor/facilitator (see SessionCallTarget).
    target_user_ids: list[UUID] = []

    class Config:
        from_attributes = True


class GenerateSessionsResponse(BaseModel):
    created: list[SessionOut]
    skipped: int


class AddSessionRequest(BaseModel):
    # A single one-off session date — for schedules that don't fit a clean
    # weekly pattern (an irregular extra session, a make-up date, etc.),
    # as a complement to the bulk weekly generator above.
    meeting_date: date
    starts_at: time | None = None
    title: str | None = None
    material_url: str | None = None
    price: Decimal | None = None


class UpdateSessionRequest(BaseModel):
    """PATCH — only the fields present are applied. Lets ops fill in a
    title/material link/price override after a session was bulk-generated
    with just a bare date."""
    meeting_date: date | None = None
    starts_at: time | None = None
    title: str | None = None
    material_url: str | None = None
    price: Decimal | None = None


class AssignInstructorRequest(BaseModel):
    user_id: UUID
    role_id: UUID | None = None


class CompleteCohortResponse(BaseModel):
    """W5 S5-2 — "completing a cohort with zero reports -> warning (not a
    block)": still 200 OK, the warning just rides along in the response
    rather than blocking the status flip."""
    cohort: CohortOut
    warnings: list[str] = []
