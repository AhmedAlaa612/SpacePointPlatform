"""Cohort-scoped instructor Missions surface (2026-08-17) —
`/missions/instructor/*`. Progress reuses `ProgressGridOut`
(`schemas/lms_progress_grid.py`) directly — same shape as the staff-only
cohort grid, just reachable by an instructor scoped to their own cohort.
Review reuses `MissionAttemptAdminOut`/`MissionAttemptReviewIn`
(`schemas/missions_admin.py`) directly, same as the mission-manager queue.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class InstructorCohortOut(BaseModel):
    id: UUID
    name: str
    program_name: str | None = None
    status: str


class MissionStepGateOut(BaseModel):
    step_key: str
    label: str
    is_unlocked: bool
    updated_at: datetime | None = None
    updated_by_name: str | None = None


class MissionStepGateUpdateIn(BaseModel):
    is_unlocked: bool
