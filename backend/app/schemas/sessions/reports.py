"""Schemas for session reports (V2 W5 S5-2) — a file + notes an instructor
or ops uploads after delivering a session, tracked on record but never
required to complete a cohort (see complete_cohort's zero-reports warning).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SessionReportOut(BaseModel):
    id: UUID
    cohort_id: UUID
    session_id: UUID | None = None
    uploaded_by: UUID | None = None
    uploaded_by_name: str | None = None
    file_url: str
    filename: str
    notes: str | None = None
    created_at: datetime
