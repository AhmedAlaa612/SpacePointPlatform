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

from pydantic import BaseModel, ConfigDict, Field

ModuleItemKind = Literal["video", "text", "quiz", "flashcards"]


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


class AdminContentQuiz(BaseModel):
    pass_threshold: int = Field(ge=0, le=100, default=0)
    mid_video_at_seconds: int | None = None
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


AdminModuleContent = Union[AdminContentQuiz, AdminContentFlashcards, AdminContentText, AdminContentVideo]


# ── courses ──────────────────────────────────────────────────────────────────

CourseLevel = Literal["beginner", "intermediate", "advanced"]


class CourseCreate(BaseModel):
    title: str
    description: str | None = None
    kind: Literal["course", "mission"] = "course"
    outcomes: list[str] = Field(default_factory=list)
    level: CourseLevel | None = None
    track: str | None = None
    instructor_id: UUID | None = None
    instructor_title: str | None = None


class CourseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    kind: Literal["course", "mission"] | None = None
    outcomes: list[str] | None = None
    level: CourseLevel | None = None
    track: str | None = None
    instructor_id: UUID | None = None
    instructor_title: str | None = None


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
