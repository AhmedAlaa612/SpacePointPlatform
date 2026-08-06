"""LMS course domain (LM1-1) — courses, modules, items, and the video state row.

Owns the authored-side of the LMS: `courses` (catalogue rows), `course_modules`
(ordered lessons inside a course), `module_items` (every content item of all
four kinds — video|text|quiz|flashcards), and `module_videos` (the one row
whose async transcode state the worker writes).

`module_items.content` is JSONB on purpose (§2 of the LMS plan): authored
content is read as a whole unit and never filtered or joined, so six
normalized tables (module_texts, module_quizzes, quiz_questions, quiz_options,
module_flashcards, flashcard_cards) bought nothing. The single cost — answer
leakage has no DB-level guard — is paid by one function
(`services/lms/serialize.py::student_view`) and its test.

Nothing here references `contacts`; everything keys on `users`, so
`MERGE_FK_REGISTRY` is untouched.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class Course(Base):
    """A published (or draft) course in the catalogue — e.g. 'CubeSat Basics'.

    `kind` is course|mission; `mission` values land in Phase 2. `created_by`
    is RESTRICT: whoever authored a course stays on the record even after
    their account is gone (same reasoning as movements.created_by).
    """

    __tablename__ = "courses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    # course|mission (mission = Phase 2)
    kind = Column(String(12), nullable=False, default="course")
    # catalog visibility; unpublished courses exist but never show in GET /lms/catalog
    is_published = Column(Boolean, nullable=False, default=False)
    created_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # ── authoring metadata (LMS redesign, 2026-08-06) — all optional, an
    # unauthored course just renders without them. See
    # LMS_REDESIGN_FOLLOWUPS.md #2 for why the course landing page needed these.
    image_bucket = Column(String(64), nullable=True)
    image_path = Column(String(512), nullable=True)
    outcomes = Column(JSONB, nullable=False, default=list)  # list[str] — "what you'll be able to do"
    level = Column(String(20), nullable=True)  # beginner|intermediate|advanced
    track = Column(String(80), nullable=True)  # free-text catalog grouping, e.g. "Spacecraft systems"
    # The public-facing instructor, deliberately distinct from created_by
    # (who authored the content — often ops, not the instructor).
    instructor_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    instructor_title = Column(String(120), nullable=True)  # e.g. "Lead Systems Engineer, SpacePoint"


class CourseModule(Base):
    """An ordered lesson inside a course. Position is the order; reordering is
    rewriting positions in one transaction, not inserting between."""

    __tablename__ = "course_modules"
    __table_args__ = (
        UniqueConstraint("course_id", "position", name="uq_course_modules_course_position"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(128), nullable=False)
    position = Column(Integer, nullable=False)


class ModuleItem(Base):
    """One content item inside a module — the atomic unit of student progress.

    `kind` is video|text|quiz|flashcards. `content` holds the authored payload
    for every kind (text body, quiz questions/options/answers, flashcard
    cards); the video kind keeps its payload empty here and the real state in
    `module_videos` (async columns the worker writes — this table stays
    sync-authored only).

    A module unlocks when every *mandatory* item of the previous module is
    completed (D6) — optional items (`is_required=False`) are skippable and
    never block unlock.
    """

    __tablename__ = "module_items"
    __table_args__ = (
        UniqueConstraint("module_id", "position", name="uq_module_items_module_position"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id = Column(UUID(as_uuid=True), ForeignKey("course_modules.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, nullable=False)
    # video|text|quiz|flashcards
    kind = Column(String(10), nullable=False)
    is_required = Column(Boolean, nullable=False, default=True)
    title = Column(String(128), nullable=True)
    # Authored payload, shapes documented in LMS_EXECUTION_PLAN.md §2.
    content = Column(JSONB, nullable=False, default=dict)


class ModuleVideo(Base):
    """The async state row for a video item — the only LMS table a worker writes.

    `source_bucket`/`source_path` are the original MP4 as uploaded, never
    served to students. Once the ARQ transcode job finishes, `playlist_path`
    (HLS .m3u8) and `key_path` (AES-128 key written through the storage facade)
    point at ready-to-serve assets and `transcode_status` flips to `ready` /
    `failed`. One row per item: `item_id` is UNIQUE.

    `transcode_status` is the one column the player must read: anything except
    `ready` renders a state card.
    """

    __tablename__ = "module_videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(
        UUID(as_uuid=True), ForeignKey("module_items.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    source_bucket = Column(String(64), nullable=False)
    source_path = Column(String(512), nullable=False)
    playlist_path = Column(String(512), nullable=True)
    key_path = Column(String(512), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    # pending|processing|ready|failed
    transcode_status = Column(String(12), nullable=False, default="pending")
    transcode_error = Column(Text, nullable=True)
