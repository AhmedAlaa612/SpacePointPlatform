"""LMS student-facing schemas (LM1-3).

The content models are the *second* enforcement of the §2 answer-leakage
guarantee. Every model is `extra="forbid"`, so a payload that retains
`is_correct` or `explanation` fails response validation instead of silently
passing — the leak the service-layer `student_view` already strips is caught
again at the response boundary (plan: "Pydantic response models on the student
routes enforce it a second time").
"""

from datetime import datetime
from typing import Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ContentText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str


class QuizOptionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


class QuizQuestionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str
    options: list[QuizOptionOut]


class ContentQuiz(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pass_threshold: int
    mid_video_at_seconds: int | None = None
    questions: list[QuizQuestionOut]


class FlashcardCardOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    term: str
    definition: str


class ContentFlashcards(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    cards: list[FlashcardCardOut]


class ContentVideo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcode_status: str | None = None
    duration_seconds: int | None = None


ModuleContent = Union[ContentQuiz, ContentText, ContentFlashcards, ContentVideo]


# ── catalog / course outline (login-only) ───────────────────────────────────

class CourseCatalogOut(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    kind: str


class ModuleLockOut(BaseModel):
    module_id: UUID
    title: str | None = None
    position: int
    locked: bool
    mandatory_total: int
    mandatory_completed: int


class CourseDetailOut(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    kind: str
    enrolled: bool
    completed: bool
    modules: list[ModuleLockOut]


# ── enrollment ──────────────────────────────────────────────────────────────

class EnrollIn(BaseModel):
    course_id: UUID


class EnrollmentOut(BaseModel):
    id: UUID
    course_id: UUID
    source: str
    status: str
    created_at: datetime | None = None


# ── module read (enrolled student only) ─────────────────────────────────────

class ModuleItemOut(BaseModel):
    id: UUID
    kind: Literal["video", "text", "quiz", "flashcards"]
    title: str | None = None
    position: int
    content: ModuleContent
    # this student's own per-item state, so the player can render progress
    status: str | None = None


class ModuleOut(BaseModel):
    id: UUID
    course_id: UUID
    title: str
    position: int
    items: list[ModuleItemOut]


# ── progress + quiz submission ──────────────────────────────────────────────

class ProgressIn(BaseModel):
    action: Literal["video-watched", "text-viewed", "quiz-attempt", "flashcards-skipped"]


class ProgressOut(BaseModel):
    status: str
    quiz_attempts: int
    best_score: float | None = None
    completed_at: datetime | None = None


class QuizAnswersIn(BaseModel):
    answers: list[int]


class QuizReviewItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str | None = None
    selected: int
    correct: bool
    explanation: str | None = None


class QuizReviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: float
    passed: bool
    pass_threshold: int
    attempts: int
    best_score: float | None = None
    questions: list[QuizReviewItemOut]