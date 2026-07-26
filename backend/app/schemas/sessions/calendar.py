"""Read-only unified calendar schemas (V2 S6-1)."""

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class CalendarInstructorOut(BaseModel):
    user_id: UUID
    full_name: str
    role: Literal["lead", "co"]


class CalendarEventOut(BaseModel):
    id: str
    source: Literal["session", "teacher_session"]
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    session_id: UUID | None = None
    cohort_id: UUID | None = None
    cohort_name: str | None = None
    program_id: UUID | None = None
    program_name: str | None = None
    program_type: str | None = None
    location: str | None = None
    staffing_status: str | None = None
    delivery_status: Literal["scheduled", "in_progress", "completed"] | None = None
    instructors: list[CalendarInstructorOut] = []
    teacher_session_status: str | None = None
    teacher_name: str | None = None


class CalendarOut(BaseModel):
    from_date: date
    to_date: date
    scope: Literal["ops", "instructor"]
    events: list[CalendarEventOut]
