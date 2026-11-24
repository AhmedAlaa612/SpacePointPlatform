"""Pydantic schemas for the LMS Interactive Books domain."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BookLessonOut(BaseModel):
    spread: str
    title_en: str
    title_ar: str | None = None
    game_keys: list[str] = []


class BookChapterOut(BaseModel):
    key: str
    code: str | None = None
    part: str | None = None
    title_en: str
    title_ar: str | None = None
    lessons: list[BookLessonOut] = []


class BookProfileOut(BaseModel):
    key: str
    label_en: str
    label_ar: str | None = None
    subtitle_en: str | None = None
    subtitle_ar: str | None = None
    default_lang: str | None = None
    groups: list[str] = []


class BookProgressOut(BaseModel):
    current_spread: str | None = None
    current_chapter: str | None = None
    active_profile: str | None = None
    visited_spreads: list[str] = []
    stars: dict[str, int] = {}
    stars_earned: int = 0
    stars_possible: int = 0
    completion_pct: int = 0
    last_read_at: datetime | None = None


class BookCatalogOut(BaseModel):
    id: UUID
    slug: str
    title: str
    title_ar: str | None = None
    subtitle: str | None = None
    author_name: str | None = None
    cover_url: str | None = None
    cover_page_url: str | None = None
    languages: list[str] = ["en"]
    access_mode: Literal["open", "invite", "paid"] = "open"
    price_cents: int | None = None
    currency: str = "usd"
    enrolled: bool = False
    is_preview: bool = False
    completion_pct: int = 0
    stars_earned: int = 0
    stars_possible: int = 0
    chapter_count: int = 0


class BookDetailOut(BookCatalogOut):
    description: str | None = None
    access_days: int | None = None
    bundle_version: int = 0
    is_published: bool = False
    default_profile: str = "all"
    outline: list[BookChapterOut] = []
    profiles: list[BookProfileOut] = []
    progress: BookProgressOut | None = None


class BookReaderSessionOut(BaseModel):
    book_id: UUID
    title: str
    title_ar: str | None = None
    bundle_version: int
    token: str
    bundle_url: str
    can_teacher: bool
    default_profile: str
    languages: list[str]
    outline: list[BookChapterOut] = []
    profiles: list[BookProfileOut] = []
    progress: BookProgressOut | None = None


class BookProgressSyncIn(BaseModel):
    current_spread: str | None = Field(default=None, max_length=128)
    current_chapter: str | None = Field(default=None, max_length=64)
    active_profile: str | None = Field(default=None, max_length=32)
    visited_spreads: list[str] | None = None
    stars: dict[str, int] | None = None
    stars_earned: int | None = Field(default=None, ge=0)
    stars_possible: int | None = Field(default=None, ge=0)
    completion_pct: int | None = Field(default=None, ge=0, le=100)
    raw_state: dict[str, Any] | None = None


class BookExerciseIn(BaseModel):
    chapter_key: str | None = Field(default=None, max_length=64)
    exercise_key: str = Field(min_length=1, max_length=160)
    exercise_type: Literal["game", "quiz", "your_turn", "notebook", "lab"]
    prompt_text: str | None = None
    answer_json: dict[str, Any] = {}
    is_correct: bool | None = None
    score_stars: int | None = Field(default=None, ge=0, le=3)
    max_stars: int | None = Field(default=None, ge=0, le=10)


class BookExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    chapter_key: str | None = None
    exercise_key: str
    exercise_type: str
    prompt_text: str | None = None
    answer_json: dict[str, Any]
    is_correct: bool | None = None
    score_stars: int | None = None
    max_stars: int | None = None
    attempts: int
    updated_at: datetime


# ── Admin / Authoring Schemas ────────────────────────────────────────────────

class BookAdminOut(BaseModel):
    id: UUID
    slug: str
    title: str
    title_ar: str | None = None
    subtitle: str | None = None
    description: str | None = None
    author_name: str | None = None
    cover_url: str | None = None
    cover_page_url: str | None = None
    languages: list[str] = ["en"]
    bundle_version: int = 0
    bundle_entry: str = "index.html"
    bundle_storage_backend: str | None = None
    bundle_size_bytes: int | None = None
    outline: list[BookChapterOut] = []
    profiles: list[BookProfileOut] = []
    default_profile: str = "all"
    access_mode: Literal["open", "invite", "paid"] = "open"
    access_days: int | None = None
    price_cents: int | None = None
    currency: str = "usd"
    is_published: bool = False
    enrollments_count: int = 0
    active_readers_count: int = 0
    avg_completion_pct: int = 0
    created_at: datetime
    updated_at: datetime


class BookCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    title_ar: str | None = Field(default=None, max_length=200)
    slug: str | None = Field(default=None, max_length=128)
    subtitle: str | None = Field(default=None, max_length=300)
    description: str | None = None
    author_name: str | None = Field(default=None, max_length=160)
    languages: list[str] = ["en"]
    access_mode: Literal["open", "invite", "paid"] = "open"
    access_days: int | None = Field(default=None, ge=1)
    price_cents: int | None = Field(default=None, ge=0)
    currency: str = Field(default="usd", min_length=3, max_length=3)
    default_profile: str = Field(default="all", max_length=32)


class BookUpdateIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    title_ar: str | None = Field(default=None, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=128)
    subtitle: str | None = Field(default=None, max_length=300)
    description: str | None = None
    author_name: str | None = Field(default=None, max_length=160)
    languages: list[str] | None = None
    access_mode: Literal["open", "invite", "paid"] | None = None
    access_days: int | None = Field(default=None, ge=1)
    price_cents: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    default_profile: str | None = Field(default=None, max_length=32)
    outline: list[dict[str, Any]] | None = None
    profiles: list[dict[str, Any]] | None = None


class BookBundleUploadOut(BaseModel):
    book_id: UUID
    bundle_version: int
    bundle_entry: str
    bundle_storage_backend: str
    bundle_size_bytes: int
    files_uploaded: int
    chapters_detected: int
    profiles_detected: int


class BookEnrollmentOut(BaseModel):
    id: UUID
    user_id: UUID
    full_name: str
    email: str
    source: str
    status: str
    expires_at: datetime | None = None
    completion_pct: int = 0
    stars_earned: int = 0
    last_read_at: datetime | None = None
    created_at: datetime


class BookEnrollmentGrantIn(BaseModel):
    user_id: UUID | None = None
    email: str | None = None


class BookBulkGrantIn(BaseModel):
    role: str = Field(min_length=1, max_length=64)


class BookBulkGrantOut(BaseModel):
    granted: int
    already_enrolled: int


class BookLearnerAnalyticsOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    completion_pct: int
    stars_earned: int
    stars_possible: int
    current_chapter: str | None = None
    exercises_answered: int
    exercises_correct: int
    notebook_count: int
    last_read_at: datetime | None = None


class BookExerciseAnalyticsOut(BaseModel):
    exercise_key: str
    chapter_key: str | None = None
    exercise_type: str
    prompt_text: str | None = None
    responses_count: int
    correct_count: int
    accuracy_pct: int | None = None
    avg_stars: float | None = None
    total_attempts: int


class BookNotebookEntryOut(BaseModel):
    user_id: UUID
    student_name: str
    student_email: str
    chapter_key: str | None = None
    exercise_key: str
    prompt_text: str | None = None
    answer_text: str
    updated_at: datetime


class BookAnalyticsOut(BaseModel):
    book_id: UUID
    total_enrolled: int
    active_readers: int
    avg_completion_pct: int
    total_responses: int
    exercise_accuracy_pct: int | None = None
    learners: list[BookLearnerAnalyticsOut] = []
    exercises: list[BookExerciseAnalyticsOut] = []
    notebooks: list[BookNotebookEntryOut] = []
