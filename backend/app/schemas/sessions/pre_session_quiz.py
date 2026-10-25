from datetime import datetime
from typing import Any, Literal
from uuid import UUID

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
    question_type: Literal["pinout_table", "mcq"] = "pinout_table"
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


class ReferenceAttachmentSchema(BaseModel):
    id: str | None = None
    title: str
    url: str
    is_file: bool = False


class PreSessionQuizPresetIn(BaseModel):
    name: str
    description: str | None = None
    question_ids: list[str] = Field(default_factory=list)
    reference_attachments: list[ReferenceAttachmentSchema] = Field(default_factory=list)
    is_active: bool = True


class PreSessionQuizPresetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None = None
    question_ids: list[str] = Field(default_factory=list)
    reference_attachments: list[dict[str, Any]] = Field(default_factory=list)
    questions: list[PreSessionQuizQuestionOut] = Field(default_factory=list)
    is_active: bool = True
    created_at: datetime | None = None


class PreSessionQuizAssignmentIn(BaseModel):
    preset_id: UUID | None = None


class PreSessionQuizAssignmentOut(BaseModel):
    level: str  # "session" | "cohort" | "program" | "none"
    preset_id: UUID | None = None
    preset_name: str | None = None
    inherited: bool = False


class PreSessionQuizAnswerIn(BaseModel):
    question_id: UUID
    selected_option_index: int | None = None
    selected_cells: list[list[int]] | None = None
    chose_other: bool = False
    other_text: str | None = None


class PreSessionQuizSubmitIn(BaseModel):
    answers: list[PreSessionQuizAnswerIn]


class PreSessionQuizReviewQuestionIn(BaseModel):
    question_id: UUID
    is_correct: bool
    review_comment: str | None = None


class PreSessionQuizAttemptOut(BaseModel):
    id: UUID
    session_id: UUID
    preset_id: UUID | None = None
    user_id: UUID
    user_name: str | None = None
    answers: list[dict[str, Any]] = Field(default_factory=list)
    auto_score: int
    final_score: int
    total_questions: int
    pending_review_count: int
    submitted_at: datetime | None = None


class SessionPreQuizStatusOut(BaseModel):
    has_quiz: bool
    preset: PreSessionQuizPresetOut | None = None
    my_attempt: PreSessionQuizAttemptOut | None = None
    all_attempts: list[PreSessionQuizAttemptOut] = Field(default_factory=list)
