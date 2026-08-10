"""LMS authoring schemas (LM1-5) — the `/lms/admin/*` input/output shapes.

Deliberately separate from `schemas/lms.py`: that file is the answer-leakage
choke point (every model there is `extra="forbid"` and strips `is_correct`/
`explanation`). These models are the *author's* view — they carry the
answers on purpose, because the author is the one writing them. Never import
these into a student-facing route.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ModuleItemKind = Literal["video", "text", "quiz", "flashcards", "attachment"]


class InstructorOptionOut(BaseModel):
    """One row for the course-authoring instructor picker (LMS redesign,
    2026-08-06) — deliberately minimal, not the full User shape."""
    id: UUID
    full_name: str
    photo_url: str | None = None


# ── authored content shapes (mirrors LMS_EXECUTION_PLAN.md §2, answers included) ──

class AdminContentText(BaseModel):
    body: str


class AdminQuizOptionIn(BaseModel):
    text: str
    is_correct: bool = False


class AdminQuizQuestionIn(BaseModel):
    prompt: str
    explanation: str | None = None
    options: list[AdminQuizOptionIn] = Field(min_length=2)

    @model_validator(mode="after")
    def _validate_correct_option(self) -> "AdminQuizQuestionIn":
        # submit_quiz/check_quiz_answer take one answer index per question
        # (services/lms/quiz.py) — multi-answer isn't a supported shape, and
        # zero correct answers is a question no student can ever pass (B3).
        correct_count = sum(1 for o in self.options if o.is_correct)
        if correct_count != 1:
            raise ValueError(
                f"quiz questions need exactly one correct option, got {correct_count}"
            )
        return self


class AdminContentQuiz(BaseModel):
    pass_threshold: int = Field(ge=0, le=100, default=0)
    questions: list[AdminQuizQuestionIn] = Field(min_length=1)


class AdminFlashcardIn(BaseModel):
    term: str
    definition: str


class AdminContentFlashcards(BaseModel):
    title: str | None = None
    cards: list[AdminFlashcardIn] = Field(min_length=1)


class AdminContentVideo(BaseModel):
    """Empty on purpose — video state lives in `module_videos` (LM1-6)."""
    model_config = ConfigDict(extra="forbid")


class AdminContentAttachment(BaseModel):
    """Empty on purpose, same reasoning as AdminContentVideo — a PDF is
    binary, so it can't ride the JSON create/update body. The upload
    endpoint (POST .../items/{id}/attachment) writes bucket/path/filename/
    size_bytes into `content` directly once the file is actually on disk,
    same two-step "create the item, then upload the file" shape video
    uses (2026-08-09). No separate table needed like module_videos — a PDF
    has no async processing step, so there's nothing to track a state
    machine for; the file reference alone is the whole story."""
    model_config = ConfigDict(extra="forbid")


AdminModuleContent = Union[
    AdminContentQuiz, AdminContentFlashcards, AdminContentText, AdminContentVideo, AdminContentAttachment,
]


# ── video checkpoints (timeline notes + mid-video quizzes, 2026-08-07) ───────
# Belong to the video item they're authored on, not a sibling module item —
# see the video_checkpoints migration docstring for why the old
# mid_video_at_seconds indirection was replaced.

CheckpointKind = Literal["note", "quiz"]
CheckpointQuestionType = Literal["mcq", "multiselect", "open"]


class AdminCheckpointNoteContent(BaseModel):
    body: str


class AdminCheckpointQuizContent(BaseModel):
    question_type: CheckpointQuestionType
    prompt: str
    explanation: str | None = None
    # Required for mcq/multiselect (answer choices), omitted for open.
    options: list[AdminQuizOptionIn] | None = None

    @model_validator(mode="after")
    def _validate_options(self) -> "AdminCheckpointQuizContent":
        if self.question_type == "open":
            if self.options:
                raise ValueError("open questions don't take options")
            return self
        if not self.options or len(self.options) < 2:
            raise ValueError(f"{self.question_type} questions need at least 2 options")
        correct_count = sum(1 for o in self.options if o.is_correct)
        if self.question_type == "mcq" and correct_count != 1:
            raise ValueError("mcq questions need exactly one correct option")
        if self.question_type == "multiselect" and correct_count < 1:
            raise ValueError("multiselect questions need at least one correct option")
        return self


class VideoCheckpointCreate(BaseModel):
    start_seconds: int = Field(ge=0)
    # Required for notes (a banner has a window); ignored for quizzes (a
    # quiz is a single moment) — enforced in the router, not here, since it
    # depends on `kind`.
    end_seconds: int | None = Field(default=None, ge=0)
    kind: CheckpointKind
    content: dict = Field(default_factory=dict)


class VideoCheckpointUpdate(BaseModel):
    start_seconds: int | None = Field(default=None, ge=0)
    end_seconds: int | None = Field(default=None, ge=0)
    content: dict | None = None


class VideoCheckpointAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    item_id: UUID
    start_seconds: int
    end_seconds: int | None
    kind: str
    content: dict


# ── courses ──────────────────────────────────────────────────────────────────

CourseLevel = Literal["beginner", "intermediate", "advanced"]
# P1-2 — open: any logged-in student self-enrols. invite: lists with a lock,
# only an admin grant (P1-5) enrols. paid: self-enrol starts a checkout
# (Stage S, not built yet — POST /lms/enroll 402s in the meantime).
CourseAccessMode = Literal["open", "invite", "paid"]


class CourseCreate(BaseModel):
    title: str
    description: str | None = None
    kind: Literal["course", "mission"] = "course"
    outcomes: list[str] = Field(default_factory=list)
    level: CourseLevel | None = None
    track: str | None = None
    instructor_id: UUID | None = None
    instructor_title: str | None = None
    access_mode: CourseAccessMode = "open"
    access_days: int | None = Field(default=None, ge=1)  # NULL = perpetual


class CourseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    kind: Literal["course", "mission"] | None = None
    outcomes: list[str] | None = None
    level: CourseLevel | None = None
    track: str | None = None
    instructor_id: UUID | None = None
    instructor_title: str | None = None
    access_mode: CourseAccessMode | None = None
    access_days: int | None = Field(default=None, ge=1)


class CourseAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    description: str | None
    kind: str
    is_published: bool
    created_by: UUID
    created_at: datetime | None
    image_url: str | None = None
    outcomes: list[str] = Field(default_factory=list)
    level: str | None = None
    track: str | None = None
    instructor_id: UUID | None = None
    instructor_name: str | None = None
    instructor_title: str | None = None
    access_mode: str = "open"
    access_days: int | None = None


# ── modules ──────────────────────────────────────────────────────────────────

class ModuleCreate(BaseModel):
    title: str
    position: int | None = None


class ModuleUpdate(BaseModel):
    title: str | None = None
    position: int | None = None


class ModuleAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    course_id: UUID
    title: str
    position: int


class ModuleReorderIn(BaseModel):
    """Full ordered id list, not a single move — same shape works for
    drag-and-drop or up/down buttons, and lets the backend rewrite positions
    in one transaction instead of racing the unique constraint two requests
    at a time."""
    module_ids: list[UUID]


# ── items ────────────────────────────────────────────────────────────────────

class ItemCreate(BaseModel):
    kind: ModuleItemKind
    title: str | None = None
    is_required: bool = True
    position: int | None = None
    content: dict = Field(default_factory=dict)


class ItemUpdate(BaseModel):
    title: str | None = None
    is_required: bool | None = None
    position: int | None = None
    content: dict | None = None


class ItemAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    module_id: UUID
    kind: str
    title: str | None
    is_required: bool
    position: int
    content: dict


class ItemReorderIn(BaseModel):
    item_ids: list[UUID]


# ── program curriculum ──────────────────────────────────────────────────────

class CurriculumEntryIn(BaseModel):
    course_id: UUID
    position: int | None = None


class CurriculumEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    program_id: UUID
    course_id: UUID
    position: int


# ── learning paths (self-paced ordered course sequences, 2026-08-08) ───────

class LearningPathCreate(BaseModel):
    title: str
    description: str | None = None


class LearningPathUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    is_published: bool | None = None


class LearningPathAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    description: str | None
    is_published: bool
    created_by: UUID
    created_at: datetime | None
    image_url: str | None = None


class LearningPathStepIn(BaseModel):
    course_id: UUID
    position: int | None = None


class LearningPathStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    learning_path_id: UUID
    course_id: UUID
    position: int


# ── enrollment admin (P1-5) ──────────────────────────────────────────────────

class EnrollmentAdminOut(BaseModel):
    id: UUID
    user_id: UUID
    student_name: str
    student_email: str
    course_id: UUID
    source: str
    status: str
    granted_by: UUID | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None


class EnrollmentGrantIn(BaseModel):
    user_id: UUID


class BulkGrantIn(BaseModel):
    """Exactly one of cohort_id (every student with an active registration in
    that cohort) or role (every user holding that role — D2, staff can take
    LMS courses too) — a one-shot iteration, never a live membership rule
    (§3: "do not build a groups/audiences table")."""
    cohort_id: UUID | None = None
    role: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "BulkGrantIn":
        if (self.cohort_id is None) == (self.role is None):
            raise ValueError("give exactly one of cohort_id or role")
        return self


class BulkGrantOut(BaseModel):
    granted: int
    already_enrolled: int
    # Only meaningful for cohort mode — a registered contact with no linked
    # LMS account. Bulk-grant doesn't create accounts; that's
    # ops_integration.sync_registration_lms's job, a separate concern.
    skipped_no_account: int = 0
