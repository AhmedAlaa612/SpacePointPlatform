"""LMS student-facing schemas (LM1-3).

The content models are the *second* enforcement of the §2 answer-leakage
guarantee. Every model is `extra="forbid"`, so a payload that retains
`is_correct` or `explanation` fails response validation instead of silently
passing — the leak the service-layer `student_view` already strips is caught
again at the response boundary (plan: "Pydantic response models on the student
routes enforce it a second time").
"""

from datetime import date, datetime
from typing import Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.curriculum import PrerequisiteItemOut


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


class ContentAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str | None = None
    size_bytes: int | None = None


class ContentMission(BaseModel):
    """P5-5 — a mission embedded in a course module. `mission_title`/
    `mission_kind`/`points`/`attempt_status` are enriched by the router
    (mirrors ContentVideo's transcode_status — not stored in `content`
    itself, looked up fresh per request)."""
    model_config = ConfigDict(extra="forbid")
    mission_id: UUID
    variant_id: UUID | None = None
    mission_title: str | None = None
    mission_kind: str | None = None
    points: int | None = None
    attempt_status: str | None = None


ModuleContent = Union[ContentQuiz, ContentText, ContentFlashcards, ContentVideo, ContentAttachment, ContentMission]


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
    access_mode: str = "open"  # P1-7 — open|invite|paid
    enrolled: bool = False  # this caller's own active, unexpired enrollment
    locked: bool = False  # 7B-2 — unmet prerequisites; independent of access_mode


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
    access_mode: str = "open"  # P1-7 — open|invite|paid, drives the CTA
    locked: bool = False  # 7B-2 — unmet prerequisites; independent of access_mode
    prerequisites: list[PrerequisiteItemOut] = []
    # Stage S — integer minor units, matching Stripe's unit_amount. NULL
    # unless access_mode == "paid".
    price_cents: int | None = None
    currency: str = "usd"


# ── enrollment ──────────────────────────────────────────────────────────────

class EnrollIn(BaseModel):
    course_id: UUID


class EnrollmentOut(BaseModel):
    id: UUID
    course_id: UUID
    source: str
    status: str
    created_at: datetime | None = None
    expires_at: datetime | None = None  # P1-3 — NULL means perpetual


# ── checkout (Stage S, Stripe) ───────────────────────────────────────────────

class CheckoutSessionOut(BaseModel):
    checkout_url: str


class CheckoutFulfillOut(BaseModel):
    status: str  # pending | paid | refunded | disputed | failed
    course_id: UUID


# ── module read (enrolled student only) ─────────────────────────────────────

class ModuleItemOut(BaseModel):
    id: UUID
    kind: Literal["video", "text", "quiz", "flashcards", "attachment", "mission"]
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
    action: Literal["video-watched", "text-viewed", "quiz-attempt", "flashcards-skipped", "attachment-viewed"]


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


class AttachmentUrlOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    filename: str | None = None


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
    # 2026-08-12 — "am I on this path", so the landing page can split
    # "your paths" from "explore". True iff the caller has an active
    # enrollment in at least one of the path's courses; `pct` alone can't
    # answer it (a freshly-started path is 0% but is still yours), which is
    # the same distinction `CourseCatalogOut.enrolled` already draws.
    enrolled: bool = False


class MyCertificateOut(BaseModel):
    """One earned LMS certificate (2026-08-13). `url` is signed at query
    time from bucket/file_path, the resolve_url pattern — never stored."""
    id: UUID
    type: str  # lms_course_completion | lms_path_completion
    title: str  # the course or learning path it was earned for
    course_id: UUID | None = None
    learning_path_id: UUID | None = None
    issued_at: datetime | None = None
    url: str | None = None


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


# ── leaderboard (P2-4) — not wired into any student-facing page yet, D6 is
# still an open operator decision (PHASE2_EXECUTION_PLAN.md §2) ────────────

class LeaderboardEntryOut(BaseModel):
    rank: int
    user_id: UUID
    display_name: str
    points: int


# ── my-programs (P4-3) — the cohort view a student cannot currently see ────

class MyProgramCourseOut(BaseModel):
    course_id: UUID
    title: str
    enrolled: bool
    progress_pct: int


class MyProgramOut(BaseModel):
    registration_id: UUID
    cohort_id: UUID
    program_name: str
    cohort_name: str
    starts_on: date | None = None
    ends_on: date | None = None
    location_name: str | None = None
    location_address: str | None = None
    instructor_name: str | None = None
    attended_sessions: int
    total_sessions: int
    courses: list[MyProgramCourseOut] = []
    missions: list = []  # Stage 5 fills this in; empty, not omitted, until then


# ── LMS Program checklist (2026-08-21 redesign) ─────────────────────────────

LmsProgramItemStatus = Literal["pending", "done", "awaiting_confirmation"]


class LmsProgramChecklistItemOut(BaseModel):
    id: UUID
    position: int
    item_type: str
    title: str
    description: str | None = None
    optional: bool
    requires_confirmation: bool
    status: LmsProgramItemStatus
    # Resolved link, whatever the item type: a course id, a mission
    # attempt id (the ops-assigned run itself, never the mission catalog
    # entry), or the stored external_url — the frontend picks which by
    # `item_type`, same shape the Poster tab already established.
    course_id: UUID | None = None
    mission_attempt_id: UUID | None = None
    # mission_id/mission_kind: which route a mission_run item's "Continue"
    # link needs — design/operate attempts have their own attempt-keyed
    # page, every other kind is viewed inline on the mission's own page.
    mission_id: UUID | None = None
    mission_kind: str | None = None
    external_url: str | None = None
    submission_prompt: str | None = None
    # What the student themself submitted back, for a `submission` item.
    submitted_url: str | None = None


class LmsProgramAssignmentSummaryOut(BaseModel):
    assignment_id: UUID
    lms_program_id: UUID
    name: str
    cohort_id: UUID | None = None
    cohort_name: str | None = None
    items_total: int
    items_done: int
    pct: int
    next_item_title: str | None = None
    certificate_required: bool
    certificate_earned: bool


class LmsProgramChecklistOut(BaseModel):
    assignment_id: UUID
    lms_program_id: UUID
    name: str
    description: str | None = None
    cohort_id: UUID | None = None
    cohort_name: str | None = None
    certificate_required: bool
    certificate_earned: bool
    items: list[LmsProgramChecklistItemOut]


class LmsProgramItemSubmitIn(BaseModel):
    url: str