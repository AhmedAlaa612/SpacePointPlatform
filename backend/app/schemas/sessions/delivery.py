"""Schemas for instructor session delivery (V2 W5 S5-1): session detail +
roster, manual attendance, QR scan, start/mark-done. Session-scoped,
matching the assignment model W4's staffing marketplace already uses.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.sessions.reports import SessionReportOut

AttendanceStatus = Literal["present", "absent", "late", "excused"]


class RosterEntryOut(BaseModel):
    registration_id: UUID
    contact_id: UUID
    student_name: str
    student_phone: str | None = None
    student_email: str | None = None
    student_date_of_birth: str | None = None
    student_grade: str | None = None
    student_organization_name: str | None = None
    att_status: AttendanceStatus | None = None
    att_method: Literal["manual", "qr"] | None = None
    recorded_at: datetime | None = None


class SessionDeliveryOut(BaseModel):
    id: UUID
    cohort_id: UUID
    cohort_name: str
    program_name: str
    location: str | None = None
    meeting_date: date
    starts_at: time | None = None
    title: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    roster: list[RosterEntryOut]
    reports: list[SessionReportOut] = []


class MarkAttendanceRequest(BaseModel):
    att_status: AttendanceStatus


class AttendanceOut(BaseModel):
    registration_id: UUID
    student_name: str
    att_status: AttendanceStatus
    method: Literal["manual", "qr"]
    recorded_at: datetime


class ScanAttendanceRequest(BaseModel):
    token: str
