"""Mission authoring schemas (P5-4) — `/missions/admin/*`.

Variant `config` validation for the `quiz` kind reuses `AdminContentQuiz`
directly (`schemas/lms_admin.py`) rather than a second copy of the same
shape/validator (exactly-one-correct-option, B3) — one place a quiz
question can be malformed, whichever surface authored it.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

MissionKind = Literal["design", "submission", "quiz", "checklist", "operate", "external"]
MissionTeamPolicy = Literal["solo", "team", "either"]
MissionStatus = Literal["draft", "in_review", "published", "archived"]
MissionAccessMode = Literal["open", "invite"]  # never 'paid' — see models/missions/mission.py


class MissionCreate(BaseModel):
    title: str
    slug: str
    summary: str | None = None
    description: str | None = None
    kind: MissionKind
    team_policy: MissionTeamPolicy = "solo"
    access_mode: MissionAccessMode = "open"
    track: str | None = None


class MissionUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    description: str | None = None
    status: MissionStatus | None = None
    access_mode: MissionAccessMode | None = None
    team_policy: MissionTeamPolicy | None = None
    track: str | None = None


class MissionVariantCreate(BaseModel):
    label: str
    position: int
    points: int = Field(ge=0)
    config: dict = {}


class MissionVariantUpdate(BaseModel):
    label: str | None = None
    position: int | None = None
    points: int | None = Field(default=None, ge=0)
    config: dict | None = None


class MissionVariantAdminOut(BaseModel):
    id: UUID
    label: str
    position: int
    points: int
    config: dict


class MissionAdminOut(BaseModel):
    id: UUID
    title: str
    slug: str
    summary: str | None = None
    description: str | None = None
    kind: str
    team_policy: str
    status: str
    access_mode: str
    track: str | None = None
    image_url: str | None = None
    authored_by: UUID
    authored_by_name: str | None = None
    reviewed_by: UUID | None = None
    created_at: datetime | None = None
    variants: list[MissionVariantAdminOut] = []


class MissionAttemptReviewIn(BaseModel):
    passed: bool
    score: float | None = None
    review_comment: str | None = None


class MissionAttemptAdminOut(BaseModel):
    id: UUID
    mission_id: UUID
    mission_title: str
    variant_id: UUID
    variant_label: str
    # user_id XOR team_id — solo attempts set the former, team attempts (P6-2)
    # the latter, mirroring mission_attempts' own CHECK constraint.
    user_id: UUID | None = None
    student_name: str | None = None
    team_id: UUID | None = None
    team_name: str | None = None
    attempt_no: int
    status: str
    score: float | None = None
    payload: dict = {}
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    decided_at: datetime | None = None


class MissionTeamCreateAdminIn(BaseModel):
    """Ops-assign (P6-4): cohort_id required — self-form (schemas/missions.py
    ::MissionTeamCreateIn) is the same primitive without one."""
    name: str
    cohort_id: UUID
    member_ids: list[UUID] = []


class MissionTeamAdminOut(BaseModel):
    id: UUID
    name: str
    cohort_id: UUID | None = None
    member_ids: list[UUID] = []
    member_names: list[str] = []


class DesignStepGateOut(BaseModel):
    step_key: str
    label: str
    is_unlocked: bool


class DesignStepGateUpdateIn(BaseModel):
    is_unlocked: bool
