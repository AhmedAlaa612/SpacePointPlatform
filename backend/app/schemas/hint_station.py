from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# ── Hint Card Schemas ────────────────────────────────────────────────────────

class CohortHintCardOut(BaseModel):
    id: UUID
    challenge_id: UUID
    level: int
    level_label: str
    badge_label: str | None = None
    title: str
    teaser: str | None = None
    revealed_content: str | None = None  # Hidden until unlocked, or shown in authoring
    point_deduction: int
    unlock_order: int
    position: int
    created_at: datetime | None = None

    # Computed state for the current requesting team
    is_revealed: bool = False
    is_locked: bool = False
    revealed_at: datetime | None = None
    revealed_by_name: str | None = None

    class Config:
        from_attributes = True


class CohortHintCardCreateIn(BaseModel):
    level: int = Field(ge=1, le=10)
    level_label: str = Field(min_length=1, max_length=64)
    badge_label: str | None = Field(default=None, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    teaser: str | None = None
    revealed_content: str = Field(min_length=1)
    point_deduction: int = Field(default=2, ge=0)
    unlock_order: int = Field(default=1, ge=1)
    position: int = Field(default=0, ge=0)


class CohortHintCardUpdateIn(BaseModel):
    level: int | None = Field(default=None, ge=1, le=10)
    level_label: str | None = Field(default=None, min_length=1, max_length=64)
    badge_label: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    teaser: str | None = None
    revealed_content: str | None = None
    point_deduction: int | None = Field(default=None, ge=0)
    unlock_order: int | None = Field(default=None, ge=1)
    position: int | None = Field(default=None, ge=0)


# ── Challenge Schemas ────────────────────────────────────────────────────────

class CohortHintChallengeOut(BaseModel):
    id: UUID
    owner_type: str  # "program" | "cohort"
    owner_id: UUID
    title: str
    challenge_code: str | None = None
    topic: str | None = None
    description: str
    mission_statement: str | None = None
    max_points: int = 20
    position: int = 0
    is_active: bool = True
    created_at: datetime | None = None
    cards: list[CohortHintCardOut] = []

    # Computed totals for the requesting team
    points_deducted: int = 0
    max_remaining_points: int = 20

    class Config:
        from_attributes = True


class CohortHintChallengeCreateIn(BaseModel):
    owner_type: str = Field(pattern="^(program|cohort)$")
    owner_id: UUID
    title: str = Field(min_length=1, max_length=255)
    challenge_code: str | None = Field(default=None, max_length=64)
    topic: str | None = Field(default=None, max_length=128)
    description: str = Field(min_length=1)
    mission_statement: str | None = None
    max_points: int = Field(default=20, ge=1)
    position: int = Field(default=0, ge=0)
    is_active: bool = True


class CohortHintChallengeUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    challenge_code: str | None = Field(default=None, max_length=64)
    topic: str | None = Field(default=None, max_length=128)
    description: str | None = None
    mission_statement: str | None = None
    max_points: int | None = Field(default=None, ge=1)
    position: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


# ── Student Surface Wrapper ──────────────────────────────────────────────────

class StudentHintStationOut(BaseModel):
    cohort_id: UUID | None = None
    cohort_name: str | None = None
    program_id: UUID | None = None
    program_name: str | None = None
    team_id: UUID | None = None
    team_name: str | None = None
    is_active: bool = True
    challenges: list[CohortHintChallengeOut] = []
    total_hints_revealed: int = 0
    total_points_deducted: int = 0
    can_switch_to_judge_view: bool = False


# ── Judging & Reveal Summary Schemas ────────────────────────────────────────

class HintRevealAuditOut(BaseModel):
    id: UUID
    challenge_id: UUID
    challenge_title: str
    hint_card_id: UUID
    level: int
    level_label: str
    card_title: str
    points_deducted: int
    revealed_at: datetime
    revealed_by_name: str | None = None


class TeamHintJudgingSummaryOut(BaseModel):
    team_id: UUID
    team_name: str
    team_code: str | None = None
    hints_used: int = 0
    total_points_deducted: int = 0
    reveals: list[HintRevealAuditOut] = []


class IndividualHintJudgingSummaryOut(BaseModel):
    user_id: UUID
    user_name: str
    user_email: str | None = None
    hints_used: int = 0
    total_points_deducted: int = 0
    reveals: list[HintRevealAuditOut] = []


class CohortHintJudgingSummaryOut(BaseModel):
    cohort_id: UUID
    cohort_name: str | None = None
    total_hints_revealed: int = 0
    total_points_deducted: int = 0
    teams: list[TeamHintJudgingSummaryOut] = []
    individuals: list[IndividualHintJudgingSummaryOut] = []


# ── Import Schema ───────────────────────────────────────────────────────────

class CohortHintImportIn(BaseModel):
    source_type: str = Field(pattern="^(program|cohort)$")
    source_id: UUID
    challenge_ids: list[UUID] | None = None
    replace_existing: bool = False
