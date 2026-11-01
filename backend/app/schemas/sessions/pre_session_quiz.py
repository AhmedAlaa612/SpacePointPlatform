from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class PinoutCellSchema(BaseModel):
    text: str = ""
    is_correct: bool = False


class PinoutRowSchema(BaseModel):
    label: str
    cells: list[PinoutCellSchema]


class PinoutTableConfigSchema(BaseModel):
    connector_name: str = "J1"
    header_subtitle: str = ""
    columns: list[str] = Field(default_factory=lambda: ["1", "2", "3"])
    rows: list[PinoutRowSchema] = Field(default_factory=list)


class McqOptionSchema(BaseModel):
    text: str
    is_correct: bool = False


class PreSessionQuizQuestionIn(BaseModel):
    topic: str = "General"
    question_type: Literal["pinout_table", "mcq", "written", "subsystem_matching"] = "pinout_table"
    title: str
    prompt: str
    image_url: str | None = None
    options: list[McqOptionSchema] = Field(default_factory=list)
    table_config: PinoutTableConfigSchema | None = None
    allow_other: bool = False
    is_other_correct: bool = False
    explanation: str | None = None
    explanation_image_url: str | None = None
    explanation_table: PinoutTableConfigSchema | None = None
    is_active: bool = True


class PreSessionQuizQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    topic: str
    question_type: str
    title: str
    prompt: str
    image_url: str | None = None
    options: list[dict[str, Any]] = Field(default_factory=list)
    table_config: dict[str, Any] | None = None
    allow_other: bool = False
    is_other_correct: bool = False
    explanation: str | None = None
    explanation_image_url: str | None = None
    explanation_table: dict[str, Any] | None = None
    is_active: bool = True
    created_at: datetime | None = None


# ── Datasheet Library Schemas ───────────────────────────────────────────────

class PreSessionQuizDatasheetIn(BaseModel):
    title: str
    url: str
    doc_type: Literal["datasheet", "user_guide", "schematic", "application_note"] = "datasheet"
    subsystem_tag: str | None = None
    description: str | None = None
    image_url: str | None = None
    page_count: int | None = None
    is_active: bool = True


class PreSessionQuizDatasheetUpdateIn(BaseModel):
    title: str | None = None
    url: str | None = None
    doc_type: Literal["datasheet", "user_guide", "schematic", "application_note"] | None = None
    subsystem_tag: str | None = None
    description: str | None = None
    image_url: str | None = None
    page_count: int | None = None
    is_active: bool | None = None


class PreSessionQuizDatasheetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    url: str
    doc_type: str
    subsystem_tag: str | None = None
    description: str | None = None
    image_url: str | None = None
    page_count: int | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── Pipeline Schemas (Datasheet Catalog, Matching & Phases) ─────────────────

class ReferenceAttachmentSchema(BaseModel):
    id: str = Field(default_factory=lambda: f"ds-{uuid4().hex[:8]}")
    title: str
    url: str
    doc_type: str = "datasheet"
    subsystem_tag: str | None = None
    description: str | None = None
    image_url: str | None = None
    is_file: bool = True


class MatchingBucketSchema(BaseModel):
    id: str
    label: str
    subtitle: str = ""
    color: Literal["purple", "emerald", "blue", "amber", "rose", "cyan"] = "purple"


class MatchingItemRuleSchema(BaseModel):
    datasheet_id: str
    correct_bucket_id: str
    explanation: str | None = None


class MatchingPhaseConfigSchema(BaseModel):
    buckets: list[MatchingBucketSchema] = Field(default_factory=list)
    items: list[MatchingItemRuleSchema] = Field(default_factory=list)


class QuizPipelinePhaseSchema(BaseModel):
    id: str = Field(default_factory=lambda: f"phase-{uuid4().hex[:6]}")
    phase_type: Literal["explore_datasheets", "subsystem_matching", "quiz"]
    title: str
    subtitle: str = ""
    instructions: list[str] = Field(default_factory=list)
    pass_percentage: int = Field(default=100, ge=0, le=100)
    cooldown_seconds: int = Field(default=0, ge=0)
    show_correct_on_fail: bool = False
    show_explanation_on_fail: bool = False
    show_bucket_target_counts: bool = True
    allow_datasheet_lookup: bool = True
    question_ids: list[str] = Field(default_factory=list)
    matching_config: MatchingPhaseConfigSchema | None = None


# ── Preset Schemas ──────────────────────────────────────────────────────────

class PreSessionQuizPresetIn(BaseModel):
    name: str
    description: str | None = None
    question_ids: list[str] = Field(default_factory=list)
    reference_attachments: list[ReferenceAttachmentSchema] = Field(default_factory=list)
    phases: list[QuizPipelinePhaseSchema] = Field(default_factory=list)
    is_active: bool = True


class PreSessionQuizPresetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    question_ids: list[str] = Field(default_factory=list)
    reference_attachments: list[dict[str, Any]] = Field(default_factory=list)
    phases: list[dict[str, Any]] = Field(default_factory=list)
    questions: list[PreSessionQuizQuestionOut] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime | None = None


# ── Assignment Schemas ──────────────────────────────────────────────────────

class PreSessionQuizAssignmentIn(BaseModel):
    preset_id: UUID | None = None


class PreSessionQuizAssignmentOut(BaseModel):
    level: str  # "session" | "cohort" | "program" | "none"
    preset_id: UUID | None = None
    preset_name: str | None = None
    inherited: bool = False


# ── Answer & Trial Submission Schemas ───────────────────────────────────────

class PreSessionQuizAnswerIn(BaseModel):
    question_id: UUID
    selected_option_index: int | None = None
    selected_cells: list[list[int]] | None = None
    chose_other: bool = False
    other_text: str | None = None
    written_text: str | None = None


class PreSessionQuizSubmitIn(BaseModel):
    answers: list[PreSessionQuizAnswerIn]


class PhaseTrialSubmitIn(BaseModel):
    client_duration_seconds: int = Field(default=0, ge=0)
    matching_placements: dict[str, str] = Field(default_factory=dict)
    answers: list[PreSessionQuizAnswerIn] = Field(default_factory=list)


class PreSessionQuizReviewQuestionIn(BaseModel):
    question_id: UUID
    is_correct: bool
    review_comment: str | None = None


class PhaseTrialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_id: UUID
    phase_id: str
    phase_index: int
    phase_type: str
    trial_number: int
    started_at: datetime
    submitted_at: datetime
    duration_seconds: int
    score: int
    total: int
    score_pct: int
    pass_percentage_required: int
    passed: bool
    cooldown_until: datetime | None = None
    cooldown_seconds_remaining: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class PreSessionQuizAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cohort_id: UUID
    session_id: UUID | None = None
    preset_id: UUID | None = None
    user_id: UUID
    user_name: str | None = None
    status: str = "in_progress"
    current_phase_index: int = 0
    phase_started_at: datetime | None = None
    locked_until: datetime | None = None
    cooldown_seconds_remaining: int | None = None
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    total_duration_seconds: int = 0
    answers: list[dict[str, Any]] = Field(default_factory=list)
    phase_states: dict[str, Any] = Field(default_factory=dict)
    auto_score: int = 0
    final_score: int = 0
    total_questions: int = 0
    pending_review_count: int = 0


class CohortPreQuizStatusOut(BaseModel):
    has_quiz: bool
    assignment_level: str = "none"
    preset: PreSessionQuizPresetOut | None = None
    my_attempt: PreSessionQuizAttemptOut | None = None
    trials: list[PhaseTrialOut] = Field(default_factory=list)
    all_attempts: list[PreSessionQuizAttemptOut] = Field(default_factory=list)


class SessionPreQuizStatusOut(CohortPreQuizStatusOut):
    pass
