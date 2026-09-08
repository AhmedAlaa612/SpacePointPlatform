"""Instructor assessment & performance ranking schemas (2026-09). See
`app/models/instructor_assessment/__init__.py` for the domain overview.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models.instructor_assessment.rating import RATING_DIMENSIONS
from app.models.instructor_assessment.ranking import RANKING_FACTORS


# ── question bank ────────────────────────────────────────────────────────

class AssessmentQuestionOptionIn(BaseModel):
    text: str
    is_correct: bool = False


class AssessmentQuestionIn(BaseModel):
    category: str
    prompt: str
    options: list[AssessmentQuestionOptionIn] = Field(min_length=2)
    critical: bool = False
    rationale: str | None = None

    @model_validator(mode="after")
    def _validate_correct_option(self) -> "AssessmentQuestionIn":
        correct = sum(1 for o in self.options if o.is_correct)
        if correct != 1:
            raise ValueError(f"a question needs exactly one correct option, got {correct}")
        return self


class AssessmentQuestionUpdate(BaseModel):
    category: str | None = None
    prompt: str | None = None
    options: list[AssessmentQuestionOptionIn] | None = None
    critical: bool | None = None
    rationale: str | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _validate_correct_option(self) -> "AssessmentQuestionUpdate":
        if self.options is not None:
            correct = sum(1 for o in self.options if o.is_correct)
            if correct != 1:
                raise ValueError(f"a question needs exactly one correct option, got {correct}")
        return self


class AssessmentQuestionOut(BaseModel):
    id: UUID
    category: str
    prompt: str
    options: list[AssessmentQuestionOptionIn]
    critical: bool
    rationale: str | None
    is_active: bool


class AssessmentQuestionImportOut(BaseModel):
    created: int
    errors: list[str]
    questions: list[AssessmentQuestionOut]


class AssessmentConfigCreate(BaseModel):
    name: str
    description: str | None = None


class AssessmentConfigUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class AssessmentConfigOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime | None
    question_count: int
    category_counts: dict[str, int]
    critical_count: int


class AssessmentConfigDetailOut(AssessmentConfigOut):
    questions: list[AssessmentQuestionOut]


# ── cohort assignment (the on/off switch) ───────────────────────────────

class AssessmentCohortAssignmentIn(BaseModel):
    config_id: UUID


class AssessmentCohortAssignmentOut(BaseModel):
    cohort_id: UUID
    config_id: UUID
    config_name: str
    assigned_by: UUID | None
    created_at: datetime | None


# ── attempts (instructor-facing) ────────────────────────────────────────

class AttemptQuestionOut(BaseModel):
    """A drawn question for display — options already in the shuffled
    presentation order; `is_correct` is never included here."""
    question_id: UUID
    category: str
    prompt: str
    options: list[str]
    critical: bool


class AttemptOut(BaseModel):
    id: UUID
    cohort_call_id: UUID
    status: Literal["in_progress", "submitted"]
    total: int
    questions: list[AttemptQuestionOut]


class AttemptAnswerIn(BaseModel):
    # question_id (str) -> the displayed option position the instructor
    # picked (0-based), or None if left blank.
    answers: dict[str, int | None]


class AttemptResultOut(BaseModel):
    id: UUID
    status: Literal["in_progress", "submitted"]
    score: int | None
    total: int
    critical_correct: int | None
    critical_total: int | None
    category_breakdown: dict[str, dict[str, int]] | None
    submitted_at: datetime | None


# ── post-program rating ─────────────────────────────────────────────────

class InstructorProgramRatingIn(BaseModel):
    dimension_scores: dict[str, int] = Field(min_length=len(RATING_DIMENSIONS), max_length=len(RATING_DIMENSIONS))
    strengths: str | None = None
    areas_for_improvement: str | None = None
    recommended: bool | None = None
    flag: Literal["none", "exceptional", "concern"] = "none"
    submit: bool = False  # False = autosaved draft, True = deliberate submit (ratchets forward)

    @model_validator(mode="after")
    def _validate_dimensions(self) -> "InstructorProgramRatingIn":
        keys = set(self.dimension_scores)
        expected = set(RATING_DIMENSIONS)
        if keys != expected:
            missing = expected - keys
            extra = keys - expected
            detail = []
            if missing:
                detail.append(f"missing {sorted(missing)}")
            if extra:
                detail.append(f"unknown {sorted(extra)}")
            raise ValueError(f"dimension_scores must cover exactly the 10 rating dimensions: {'; '.join(detail)}")
        for key, value in self.dimension_scores.items():
            if not (1 <= value <= 5):
                raise ValueError(f"'{key}' must be between 1 and 5, got {value}")
        return self


class InstructorProgramRatingOut(BaseModel):
    id: UUID
    cohort_id: UUID
    instructor_user_id: UUID
    rater_user_id: UUID | None
    dimension_scores: dict[str, int]
    overall_rating: float  # computed at read time — never stored
    strengths: str | None
    areas_for_improvement: str | None
    recommended: bool | None
    flag: Literal["none", "exceptional", "concern"]
    submitted: bool
    created_at: datetime | None
    submitted_at: datetime | None


# ── certifications ───────────────────────────────────────────────────────

class CertificationTagIn(BaseModel):
    label: str


class CertificationTagOut(BaseModel):
    id: UUID
    label: str
    created_at: datetime | None


# ── performance aggregation (read-only, derived) ────────────────────────

class QuizHistoryEntryOut(BaseModel):
    attempt_id: UUID
    cohort_id: UUID
    program_name: str
    score: int | None
    total: int
    critical_correct: int | None
    critical_total: int | None
    submitted_at: datetime | None


class RatingHistoryEntryOut(BaseModel):
    rating_id: UUID
    cohort_id: UUID
    program_name: str
    rater_name: str | None
    overall_rating: float
    recommended: bool | None
    flag: Literal["none", "exceptional", "concern"]
    submitted_at: datetime | None


class InstructorPerformanceOut(BaseModel):
    user_id: UUID
    total_sessions_delivered: int
    total_hours_delivered: float
    programs_participated_in: int
    average_rating: float | None
    recent_rating_trend: list[float]  # last-N overall ratings, oldest first
    reliability_ratio: float | None  # present+approved / total assigned days
    certifications: list[CertificationTagOut]
    quiz_history: list[QuizHistoryEntryOut]
    rating_history: list[RatingHistoryEntryOut]


# ── ranking weights ──────────────────────────────────────────────────────

class RankingWeightProfileIn(BaseModel):
    name: str
    factor_weights: dict[str, float] = Field(min_length=len(RANKING_FACTORS), max_length=len(RANKING_FACTORS))

    @model_validator(mode="after")
    def _validate_factors(self) -> "RankingWeightProfileIn":
        if set(self.factor_weights) != set(RANKING_FACTORS):
            raise ValueError(f"factor_weights must cover exactly: {sorted(RANKING_FACTORS)}")
        return self


class RankingWeightProfileOut(BaseModel):
    id: UUID
    name: str
    factor_weights: dict[str, float]
    is_active: bool
    updated_at: datetime | None
