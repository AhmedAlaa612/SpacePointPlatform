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
    program_id: UUID
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


class DesignStepSelectionOut(BaseModel):
    step_key: str
    label: str
    included: bool
    prereqs: list[str]  # direct prereqs only — the frontend derives its own closures from this


class DesignStepSelectionsOut(BaseModel):
    is_default: bool  # True = no rows persisted, cohort uses every step
    steps: list[DesignStepSelectionOut]
    downlink_deps: list[str]
    downlink_included: bool


class DesignStepSelectionUpdateIn(BaseModel):
    step_keys: list[str]  # desired direct selection, pre-expansion — server expands authoritatively
