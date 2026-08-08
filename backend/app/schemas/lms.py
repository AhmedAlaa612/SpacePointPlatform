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


# ── video checkpoints (timeline notes + mid-video quizzes, 2026-08-07) ───────

class CheckpointNoteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str


class CheckpointQuizOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_type: Literal["mcq", "multiselect", "open"]
    prompt: str
    # None for open questions — nothing to choose from.
    options: list[QuizOptionOut] | None = None


CheckpointContent = Union[CheckpointNoteOut, CheckpointQuizOut]


class VideoCheckpointOut(BaseModel):
    id: UUID
    start_seconds: int
    end_seconds: int | None = None
    kind: Literal["note", "quiz"]
    content: CheckpointContent


class CheckpointAnswerIn(BaseModel):
    # int (mcq), list[int] (multiselect), or str (open) — validated against
    # the checkpoint's actual question_type server-side, same "don't trust
    # the client's own shape" posture as QuizAnswersIn.
    answer: int | list[int] | str


class CheckpointAnswerOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # None for open questions (not graded) or if the student skipped.
    correct: bool | None = None
    explanation: str | None = None


# ── catalog / course outline (login-only) ───────────────────────────────────

class CourseCatalogOut(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    kind: str
    image_url: str | None = None
    level: str | None = None
    track: str | None = None


# ── my-courses dashboard (student, LMS redesign 2026-08-06) ────────────────

class DashboardStatsOut(BaseModel):
    in_progress: int
    total_enrolled: int
    modules_done: int


class ResumePointerOut(BaseModel):
    course_id: UUID
    course_title: str
    module_id: UUID
    module_title: str
    next_item_id: UUID | None = None
    mandatory_completed: int
    mandatory_total: int


class DashboardCourseOut(BaseModel):
    course_id: UUID
    title: str
    kind: str
    status: str  # not_started | in_progress | completed
    modules_done: int
    modules_total: int
    pct: int


class MyCoursesOut(BaseModel):
    stats: DashboardStatsOut
    resume: ResumePointerOut | None = None
    courses: list[DashboardCourseOut]


class ActivityItemOut(BaseModel):
    item_id: UUID
    item_title: str | None = None
    item_kind: str
    course_id: UUID
    course_title: str
    completed_at: datetime | None = None


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
    image_url: str | None = None
    outcomes: list[str] = []
    level: str | None = None
    track: str | None = None
    instructor_name: str | None = None
    instructor_title: str | None = None
    instructor_photo_url: str | None = None


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


class QuizAnswerCheckIn(BaseModel):
    question_index: int
    answer: int


class QuizAnswerCheckOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correct: bool
    explanation: str | None = None
    correct_text: str | None = None


class QuizReviewItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str | None = None
    selected: int
    correct: bool
    explanation: str | None = None
    correct_text: str | None = None


class QuizReviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: float
    passed: bool
    pass_threshold: int
    attempts: int
    best_score: float | None = None
    questions: list[QuizReviewItemOut]


# ── learning paths (self-paced ordered course sequences, 2026-08-08) ───────

class LearningPathCatalogOut(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    image_url: str | None = None
    course_count: int
    mission_count: int
    total_duration_seconds: int
    pct: int


class LearningPathStepOut(BaseModel):
    position: int
    course_id: UUID
    title: str
    kind: str
    state: Literal["done", "current", "mission", "locked"]
    pct: int
    modules_done: int
    modules_total: int


class LearningPathDetailOut(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    image_url: str | None = None
    pct: int
    course_count: int
    mission_count: int
    total_duration_seconds: int
    steps: list[LearningPathStepOut]