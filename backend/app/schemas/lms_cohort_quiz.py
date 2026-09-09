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
    time_limit_seconds: int = Field(gt=0)
    bloom_level: str | None = None
    question_type: str | None = None
    prompt: str
    options: list[CohortQuizQuestionOptionIn] = Field(min_length=2)
    explanation: str | None = None
    source_url: str | None = None

    @model_validator(mode="after")
    def _validate_correct_option(self) -> "CohortQuizQuestionIn":
        correct = sum(1 for o in self.options if o.is_correct)
        if correct != 1:
            raise ValueError(f"a question needs exactly one correct option, got {correct}")
        return self


class CohortQuizQuestionUpdate(BaseModel):
    topic: str | None = None
    subtopic: str | None = None
    difficulty: Literal["Easy", "Medium", "Hard"] | None = None
    time_limit_seconds: int | None = Field(default=None, gt=0)
    bloom_level: str | None = None
    question_type: str | None = None
    prompt: str | None = None
    options: list[CohortQuizQuestionOptionIn] | None = Field(default=None, min_length=2)
    explanation: str | None = None
    source_url: str | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _validate_correct_option(self) -> "CohortQuizQuestionUpdate":
        if self.options is not None:
            correct = sum(1 for o in self.options if o.is_correct)
            if correct != 1:
                raise ValueError(f"a question needs exactly one correct option, got {correct}")
        return self


class CohortQuizQuestionOut(BaseModel):
    id: UUID
    topic: str
    subtopic: str | None
    difficulty: str
    time_limit_seconds: int
    bloom_level: str | None
    question_type: str | None
    prompt: str
    options: list[CohortQuizQuestionOptionIn]
    explanation: str | None
    source_url: str | None
    is_active: bool


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


# ── attempts (student-facing) ───────────────────────────────────────────

class CohortQuizAttemptQuestionOut(BaseModel):
    """A question for display — options already in the shuffled
    presentation order; `is_correct` is never included here."""
    question_id: UUID
    topic: str
    difficulty: str
    time_limit_seconds: int
    prompt: str
    options: list[str]


class CohortQuizAttemptOut(BaseModel):
    id: UUID
    program_item_id: UUID
    status: Literal["in_progress", "submitted"]
    total: int
    questions: list[CohortQuizAttemptQuestionOut]


class CohortQuizAnswerIn(BaseModel):
    question_id: UUID
    # The DISPLAYED option position the student picked (0-based), or None
    # if left blank/timed out.
    selected_option_index: int | None = None
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
    options: list[str]
    selected_index: int | None
    correct_index: int
    is_correct: bool
    explanation: str | None


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
