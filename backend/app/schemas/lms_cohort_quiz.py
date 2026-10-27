"""Cohort knowledge-quiz schemas (2026-09). See
`app/models/lms/cohort_quiz.py` for the domain overview.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ── question bank ────────────────────────────────────────────────────────

class CohortQuizQuestionOptionIn(BaseModel):
    text: str
    is_correct: bool = False


class CohortQuizQuestionIn(BaseModel):
    topic: str
    subtopic: str | None = None
    difficulty: Literal["Easy", "Medium", "Hard"]
    time_limit_seconds: int = Field(default=15, ge=0)
    bloom_level: str | None = None
    question_type: str | None = "mcq"
    is_optional: bool = False
    prompt: str
    options: list[CohortQuizQuestionOptionIn] = Field(default_factory=list)
    explanation: str | None = None
    source_url: str | None = None

    @model_validator(mode="after")
    def _validate_correct_option(self) -> "CohortQuizQuestionIn":
        q_type = self.question_type or "mcq"
        if q_type == "textarea":
            return self
        if len(self.options) < 2:
            raise ValueError("a selection question needs at least 2 options")
        correct = sum(1 for o in self.options if o.is_correct)
        if q_type == "mcq" and correct > 1:
            raise ValueError(f"a single choice question cannot have more than one correct option, got {correct}")
        return self


class CohortQuizQuestionUpdate(BaseModel):
    topic: str | None = None
    subtopic: str | None = None
    difficulty: Literal["Easy", "Medium", "Hard"] | None = None
    time_limit_seconds: int | None = Field(default=None, ge=0)
    bloom_level: str | None = None
    question_type: str | None = None
    is_optional: bool | None = None
    prompt: str | None = None
    options: list[CohortQuizQuestionOptionIn] | None = None
    explanation: str | None = None
    source_url: str | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _validate_correct_option(self) -> "CohortQuizQuestionUpdate":
        q_type = self.question_type or "mcq"
        if self.options is not None:
            if q_type == "textarea":
                return self
            if len(self.options) < 2:
                raise ValueError("a selection question needs at least 2 options")
            correct = sum(1 for o in self.options if o.is_correct)
            if q_type == "mcq" and correct > 1:
                raise ValueError(f"a single choice question cannot have more than one correct option, got {correct}")
        return self


class CohortQuizQuestionOut(BaseModel):
    id: UUID
    topic: str
    subtopic: str | None
    difficulty: str
    time_limit_seconds: int
    bloom_level: str | None
    question_type: str | None = "mcq"
    is_optional: bool = False
    prompt: str
    options: list[CohortQuizQuestionOptionIn] = Field(default_factory=list)
    explanation: str | None
    source_url: str | None
    is_active: bool
    organization_id: UUID | None = None


class CohortQuizQuestionImportOut(BaseModel):
    created: int
    # Rows skipped because a question with the same prompt text already
    # exists in the bank — makes re-uploading the same file after fixing a
    # few error rows safe, instead of duplicating every already-imported row.
    skipped_duplicates: int
    errors: list[str]
    questions: list[CohortQuizQuestionOut]


# ── templates (the fixed, hand-picked question set) ─────────────────────

class CohortQuizTemplateCreate(BaseModel):
    name: str
    description: str | None = None


class CohortQuizTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class CohortQuizTemplateOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime | None
    question_count: int
    organization_id: UUID | None = None


class CohortQuizTemplateQuestionIn(BaseModel):
    question_id: UUID


class CohortQuizTemplateQuestionOut(BaseModel):
    id: UUID
    position: int
    question: CohortQuizQuestionOut


class CohortQuizTemplateDetailOut(CohortQuizTemplateOut):
    questions: list[CohortQuizTemplateQuestionOut]


class CohortQuizTemplateReorderIn(BaseModel):
    # Ids of the template's own CohortQuizTemplateQuestion rows, in the new
    # order — same full-list idiom as LmsProgramItemReorderIn.
    template_question_ids: list[UUID]


class CohortQuizTemplateGenerateIn(BaseModel):
    # Replaces the template's entire current question list with a fresh
    # round-robin-across-topics pick — "Regenerate" in the admin UI is
    # just calling this again.
    count: int = Field(gt=0, le=200)
    # None means draw from every active topic in the bank.
    topics: list[str] | None = None


# ── attempts (student-facing) ───────────────────────────────────────────

class CohortQuizAttemptQuestionOut(BaseModel):
    """A question for display — options already in the shuffled
    presentation order; `is_correct` is never included here."""
    question_id: UUID
    topic: str
    difficulty: str
    time_limit_seconds: int
    prompt: str
    options: list[str] = Field(default_factory=list)
    question_type: str = "mcq"
    is_optional: bool = False


class CohortQuizAttemptOut(BaseModel):
    id: UUID
    program_item_id: UUID
    status: Literal["in_progress", "submitted"]
    total: int
    questions: list[CohortQuizAttemptQuestionOut]


class CohortQuizAnswerIn(BaseModel):
    question_id: UUID
    # The DISPLAYED option position the student picked (0-based) for single-choice,
    # or None if left blank/timed out/textarea question.
    selected_option_index: int | None = None
    # For multiple-choice (multiselect): the list of displayed positions picked.
    selected_option_indices: list[int] | None = None
    text_answer: str | None = None
    time_taken_seconds: int | None = None
    timed_out: bool = False


class CohortQuizSubmitIn(BaseModel):
    # All at once, not per-question — same shape as instructor_assessment's
    # AttemptAnswerIn; there's no per-question submit endpoint anywhere in
    # this codebase to mirror instead.
    answers: list[CohortQuizAnswerIn]


class CohortQuizQuestionReviewOut(BaseModel):
    """Revealed only after the attempt is submitted."""
    question_id: UUID
    topic: str
    prompt: str
    options: list[str] = Field(default_factory=list)
    selected_index: int | None = None
    selected_indices: list[int] = Field(default_factory=list)
    correct_index: int | None = None
    correct_indices: list[int] = Field(default_factory=list)
    is_correct: bool | None = None
    explanation: str | None = None
    # How long the student took (client-tracked, never server-validated —
    # same trust posture the rest of this domain's timing already has) and
    # whether it was a timeout auto-submit rather than an explicit pick.
    time_taken_seconds: int | None = None
    timed_out: bool = False
    question_type: str = "mcq"
    text_answer: str | None = None
    is_optional: bool = False


class CohortQuizResultOut(BaseModel):
    id: UUID
    status: Literal["in_progress", "submitted"]
    score: int | None
    total: int
    topic_breakdown: dict[str, dict[str, int]] | None
    submitted_at: datetime | None
    questions: list[CohortQuizQuestionReviewOut]


# ── strengths & weaknesses (read-only, derived) ─────────────────────────

class CohortQuizTopicBreakdownOut(BaseModel):
    topic_breakdown: dict[str, dict[str, int]]
