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
