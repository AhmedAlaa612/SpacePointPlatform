"""Mission student-facing schemas (P5-4).

`config` on a variant is the *second* enforcement of the answer-leakage
guarantee `services/missions/serialize.py::variant_student_view` already
applies — `MissionQuizConfigOut`/`MissionEmptyConfigOut` are both
`extra="forbid"`, so a payload that retains `is_correct` fails response
validation instead of silently passing (same posture as `schemas/lms.py`).
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.lms import QuizQuestionOut, QuizReviewItemOut


class MissionQuizConfigOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pass_threshold: int
    questions: list[QuizQuestionOut]


class MissionEmptyConfigOut(BaseModel):
    model_config = ConfigDict(extra="forbid")


MissionVariantConfig = MissionQuizConfigOut | MissionEmptyConfigOut


class MissionVariantSummaryOut(BaseModel):
    id: UUID
    label: str
    position: int
    points: int


class MissionVariantOut(BaseModel):
    id: UUID
    label: str
    position: int
    points: int
    config: MissionVariantConfig


class MissionPrerequisiteOut(BaseModel):
    mission_id: UUID
    title: str
    satisfied: bool


class MissionCatalogOut(BaseModel):
    id: UUID
    title: str
    slug: str
    summary: str | None = None
    kind: str
    track: str | None = None
    image_url: str | None = None
    variants: list[MissionVariantSummaryOut]
    locked: bool = False
    team_policy: str = "solo"


class MissionGraphNodeOut(BaseModel):
    id: UUID
    title: str
    kind: str
    track: str | None = None
    locked: bool
    requires: list[UUID] = []


class MissionAttemptOut(BaseModel):
    id: UUID
    mission_id: UUID
    variant_id: UUID
    variant_label: str
    attempt_no: int
    status: str
    score: float | None = None
    payload: dict = {}
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    decided_at: datetime | None = None
    # P6-4 — set only for a team attempt (mutually exclusive with a solo one).
    team_id: UUID | None = None
    team_name: str | None = None


class MissionTeamOut(BaseModel):
    id: UUID
    name: str
    cohort_id: UUID | None = None
    member_ids: list[UUID] = []
    member_names: list[str] = []


class MissionTeamCreateIn(BaseModel):
    name: str
    member_ids: list[UUID] = []


class MissionDetailOut(BaseModel):
    id: UUID
    title: str
    slug: str
    summary: str | None = None
    description: str | None = None
    kind: str
    track: str | None = None
    image_url: str | None = None
    variants: list[MissionVariantOut]
    attempts: list[MissionAttemptOut]
    prerequisites: list[MissionPrerequisiteOut] = []
    locked: bool = False
    team_policy: str = "solo"
    my_teams: list[MissionTeamOut] = []


class MissionAttemptStartIn(BaseModel):
    variant_id: UUID
    team_id: UUID | None = None


class MissionAttemptSubmitIn(BaseModel):
    # submission kind
    artifact_url: str | None = None
    notes: str | None = None
    # quiz kind
    answers: list[int] | None = None


class MissionQuizReviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: float
    passed: bool
    questions: list[QuizReviewItemOut]


class MissionAttemptSubmitOut(BaseModel):
    attempt: MissionAttemptOut
    review: MissionQuizReviewOut | None = None  # quiz kind only — the submission kind awaits review
