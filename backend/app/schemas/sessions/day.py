"""Schemas for the instructor daily loop (operations process doc §4-§12).

See `services/sessions/day.py` for the flow these describe.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.sessions.cohorts import StaffingStatus

AttendanceStatus = Literal["present", "absent"]
DayStatus = Literal["draft", "submitted", "changes_required", "approved"]


# ── checklist templates (ops) ───────────────────────────────────────────────

class ChecklistAttachmentIn(BaseModel):
    id: str | None = None
    type: Literal["material", "link"] = "link"
    material_id: UUID | None = None
    title: str | None = None
    url: str | None = None


class ChecklistAttachmentOut(BaseModel):
    id: str | None = None
    type: Literal["material", "link"] = "link"
    material_id: UUID | None = None
    title: str | None = None
    url: str | None = None
    is_file: bool = False
    is_published: bool = True
    has_access: bool = True
    access_denied_message: str | None = None


class ChecklistItemIn(BaseModel):
    title: str
    description: str | None = None
    # §5: this item can't be ticked off without a photo/screenshot attached.
    requires_proof: bool = False
    # A non-required item is a prompt, not a gate — it never blocks submission.
    is_required: bool = True
    sort_order: int | None = None
    target_audience: str = "instructor"
    material_id: UUID | None = None
    link_url: str | None = None
    attachments: list[ChecklistAttachmentIn] = []


class SetChecklistItemsIn(BaseModel):
    """Whole-set replace, like `SetOpeningsIn` — the client never has to diff."""
    items: list[ChecklistItemIn] = []


class ChecklistItemOut(BaseModel):
    id: UUID
    program_id: UUID | None = None
    cohort_id: UUID | None = None
    session_id: UUID | None = None
    role_id: UUID | None = None
    title: str
    description: str | None = None
    requires_proof: bool
    is_required: bool
    sort_order: int
    target_audience: str = "instructor"
    material_id: UUID | None = None
    link_url: str | None = None
    attachments: list[ChecklistAttachmentOut] = []

    class Config:
        from_attributes = True


class OpsChecklistItemOut(BaseModel):
    item_id: UUID
    title: str
    description: str | None = None
    requires_proof: bool
    is_required: bool
    sort_order: int
    target_audience: str = "internal"
    material_id: UUID | None = None
    material_title: str | None = None
    material_url: str | None = None
    material_is_file: bool = False
    link_url: str | None = None
    attachments: list[ChecklistAttachmentOut] = []
    is_done: bool = False
    proof_report_id: UUID | None = None
    proof_url: str | None = None
    note: str | None = None
    completed_by: UUID | None = None
    completed_by_name: str | None = None
    updated_at: datetime | None = None


class OpsChecklistProgressIn(BaseModel):
    is_done: bool
    proof_report_id: UUID | None = None
    note: str | None = None


# ── the instructor's day ────────────────────────────────────────────────────

class CheckInIn(BaseModel):
    att_status: AttendanceStatus
    # Only meaningful with "absent"; ignored otherwise.
    reason: str | None = None


class ChecklistProgressIn(BaseModel):
    is_done: bool | None = None
    # A `session_reports` row id — proof reuses the existing upload path
    # rather than a second one. Upload first, then point at it.
    proof_report_id: UUID | None = None
    note: str | None = None


class SubmitDayIn(BaseModel):
    # §8's end-of-day feedback, one box rather than seven named fields.
    notes: str | None = None


class ChecklistLineOut(BaseModel):
    item_id: UUID
    title: str
    description: str | None = None
    requires_proof: bool
    is_required: bool
    sort_order: int
    is_done: bool
    note: str | None = None
    proof_report_id: UUID | None = None
    # Signed URL, minted per request — never stored.
    proof_url: str | None = None
    attachments: list[ChecklistAttachmentOut] = []


class DayDetailOut(BaseModel):
    """One instructor's day: what the session portal renders, and what the ops
    review card opens."""
    day_id: UUID
    session_id: UUID
    user_id: UUID
    att_status: AttendanceStatus | None = None
    absence_reason: str | None = None
    checked_in_at: datetime | None = None
    status: DayStatus
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    review_comment: str | None = None
    instructor_notes: str | None = None
    checklist: list[ChecklistLineOut] = []
    can_submit: bool = False
    # Everything still outstanding, so the instructor sees it at once rather
    # than one failed submit at a time.
    missing: list[str] = []


# ── ops review ──────────────────────────────────────────────────────────────

class DayReviewOut(BaseModel):
    """One card in the ops Day Reviews queue."""
    day_id: UUID
    session_id: UUID
    cohort_id: UUID
    cohort_name: str
    program_name: str
    session_title: str | None = None
    meeting_date: date
    user_id: UUID
    full_name: str
    att_status: AttendanceStatus | None = None
    absence_reason: str | None = None
    checked_in_at: datetime | None = None
    status: DayStatus
    submitted_at: datetime | None = None
    review_comment: str | None = None
    instructor_notes: str | None = None
    checklist_done: int
    checklist_total: int


class ReturnDayIn(BaseModel):
    # Mandatory: "changes required" with no reason is the exact thing this
    # replaces from WhatsApp.
    comment: str = Field(min_length=1)


class DayActionOut(BaseModel):
    day_id: UUID
    status: DayStatus
    review_comment: str | None = None
    # Whether approving this day was the one that completed the cohort — lets
    # ops see the knock-on (certificates, payment drafts) without polling.
    cohort_completed: bool = False


# ── the ops session board (2026-08-28) ──────────────────────────────────────

class BoardInstructorOut(BaseModel):
    """One assigned instructor's state on a Running session card — enough to
    spot "hasn't checked in" or "still mid-checklist" without opening the
    session. `day_status` is `None` for someone who hasn't touched anything
    yet (no `InstructorSessionDay` row at all)."""
    user_id: UUID
    full_name: str
    checklist_done: int
    checklist_total: int
    att_status: AttendanceStatus | None = None
    checked_in_at: datetime | None = None
    day_status: DayStatus | None = None


class BoardSessionOut(BaseModel):
    session_id: UUID
    cohort_id: UUID
    cohort_name: str
    program_name: str
    title: str | None = None
    location: str | None = None
    meeting_date: date
    starts_at: time | None = None
    staffing_status: StaffingStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    # Populated for Running and Done — a session can be marked done while an
    # instructor's own report is still unfinished, and that has to stay
    # visible somewhere on the board rather than disappearing with the card.
    instructors: list[BoardInstructorOut] = []


class SessionBoardOut(BaseModel):
    running: list[BoardSessionOut]
    done: list[BoardSessionOut]
    # Total Done sessions that exist, not just this page — the frontend's
    # "load more" needs this to know when to stop offering it.
    done_total: int
