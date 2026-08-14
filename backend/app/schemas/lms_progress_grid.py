"""Admin progress grid (7B-1, Missions Phase 2B) — every student in one
cohort x every course/mission the cohort touches, completion at a glance.
Course and mission cells have different shapes (a course is a %, a mission
is a status), so they're kept in two separate dicts rather than forced into
one common shape.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class ProgressGridCourseOut(BaseModel):
    course_id: UUID
    title: str


class ProgressGridMissionOut(BaseModel):
    mission_id: UUID
    title: str


class CourseCellOut(BaseModel):
    enrolled: bool
    pct: int


class MissionCellOut(BaseModel):
    status: str  # in_progress|submitted|passed|failed|abandoned
    score: float | None = None
    attempt_no: int
    # Design v2 (7D-9) — per-step entry state for `design` missions, so the
    # grid can say "stuck on the link budget" instead of "in progress".
    # None for every other mission kind.
    steps: dict[str, bool] | None = None


class ProgressGridRowOut(BaseModel):
    user_id: UUID
    full_name: str
    # keyed by str(course_id) / str(mission_id) — only columns that actually
    # apply appear; a course the student isn't enrolled in still gets a cell
    # (enrolled=False), a mission never attempted has no key at all.
    courses: dict[str, CourseCellOut]
    missions: dict[str, MissionCellOut]


class ProgressGridOut(BaseModel):
    cohort_id: UUID
    courses: list[ProgressGridCourseOut]
    missions: list[ProgressGridMissionOut]
    rows: list[ProgressGridRowOut]


# ── all-students single-item views (2026-08-12) ─────────────────────────────

class CourseProgressRowOut(BaseModel):
    user_id: UUID
    full_name: str
    pct: int


class CourseProgressAllOut(BaseModel):
    course_id: UUID
    course_title: str
    rows: list[CourseProgressRowOut]


class MissionProgressRowOut(BaseModel):
    user_id: UUID
    full_name: str
    status: str
    score: float | None = None
    attempt_no: int
    # Who this student is, not just their id — school/grade/code are what
    # make the table usable at a camp, where the actionable finding is
    # usually about a cohort rather than an individual.
    school_name: str | None = None
    grade: str | None = None
    invitation_code_used: str | None = None
    started_at: str | None = None
    # Per-step entry state; None for mission kinds with no step model.
    steps: dict[str, bool] | None = None


class MissionStepLabelOut(BaseModel):
    key: str
    label: str


class MissionProgressAllOut(BaseModel):
    mission_id: UUID
    mission_title: str
    # The step columns to render, in order. Empty for kinds without steps —
    # sent by the server so the table's columns can never drift from the
    # booleans the rows actually carry.
    step_labels: list[MissionStepLabelOut] = []
    has_steps: bool = False
    rows: list[MissionProgressRowOut]


# ── overview lists (2026-08-14) — the landing view for each progress tab,
# so picking an item to drill into doesn't start from a blind dropdown.

class CourseOverviewRowOut(BaseModel):
    course_id: UUID
    title: str
    enrolled_count: int
    completed_count: int
    completion_pct: int


class MissionOverviewRowOut(BaseModel):
    mission_id: UUID
    title: str
    kind: str
    attempted_count: int
    passed_count: int
    completion_pct: int
