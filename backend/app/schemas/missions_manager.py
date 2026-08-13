"""Mission-manager scoped permission schemas (7B-7)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class MissionManagerAssignIn(BaseModel):
    user_id: UUID


class MissionManagerOut(BaseModel):
    user_id: UUID
    full_name: str
    granted_by: UUID | None = None
    created_at: datetime | None = None


class MissionStatsRowOut(BaseModel):
    user_id: UUID
    full_name: str
    status: str  # in_progress|submitted|passed|failed|abandoned
    score: float | None = None
    attempt_no: int


class MissionStatsOut(BaseModel):
    mission_id: UUID
    total_attempts: int
    total_students: int
    passed_students: int
    pass_rate: int
    rows: list[MissionStatsRowOut]


class MyManagedMissionOut(BaseModel):
    mission_id: UUID
    title: str


class MissionContentOut(BaseModel):
    """Design v2 (7D-8) — the explanatory copy a mission manager may edit
    on a published mission, alongside the authored default for each field
    so an editor can always see what they changed."""

    mission_id: UUID
    mission_kind: str
    mission_status: str
    editable: dict = {}


class MissionContentUpdateIn(BaseModel):
    content: dict = {}
