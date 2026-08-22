"""Instructor LMS progress schemas (LM1-10) — response shape for
`GET /sessions/{session_id}/lms-progress`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ModuleProgressOut(BaseModel):
    module_id: UUID
    title: str | None = None
    position: int
    locked: bool
    mandatory_total: int
    mandatory_completed: int


class QuizProgressOut(BaseModel):
    item_id: UUID
    title: str | None = None
    status: str
    attempts: int
    best_score: float | None = None


class CourseProgressOut(BaseModel):
    course_id: UUID
    course_title: str | None = None
    completed: bool
    modules: list[ModuleProgressOut]
    quizzes: list[QuizProgressOut]


class StudentLmsProgressOut(BaseModel):
    contact_id: UUID
    student_name: str
    has_lms_account: bool
    courses: list[CourseProgressOut]


class SessionLmsProgressOut(BaseModel):
    session_id: UUID
    cohort_id: UUID
    program_name: str
    students: list[StudentLmsProgressOut]


class PendingConfirmationOut(BaseModel):
    item_id: UUID
    title: str
    submitted_url: str | None = None


class LmsAssignmentItemDetailOut(BaseModel):
    """Every item on one student's checklist assignment — the "detailed
    submissions" drill-in (operator ask, 2026-08-22), not just the ones
    awaiting confirmation `LmsProgramRosterRowOut.pending_confirmations`
    already carries. `GET /lms/instructor/cohorts/{cohort_id}/
    program-progress/{assignment_id}/items`."""
    item_id: UUID
    title: str
    item_type: str
    status: str
    submitted_url: str | None = None
    completed_at: datetime | None = None
    mission_attempt_id: UUID | None = None
    confirmed_by_user_id: UUID | None = None


class LmsProgramRosterRowOut(BaseModel):
    """One student's LMS Program checklist progress, instructor/ops view
    (2026-08-21) — `GET /lms/instructor/cohorts/{cohort_id}/program-progress`.
    `pending_confirmations` is what the confirm action's item picker on the
    roster row needs — the aggregate items_done/items_total alone can't
    tell you *which* item to confirm."""
    assignment_id: UUID
    user_id: UUID
    student_name: str
    name: str
    items_total: int
    items_done: int
    pct: int
    next_item_title: str | None = None
    certificate_required: bool
    certificate_earned: bool
    pending_confirmations: list[PendingConfirmationOut] = []
