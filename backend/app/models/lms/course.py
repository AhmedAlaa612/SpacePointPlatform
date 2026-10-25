"""LMS course domain (LM1-1) — courses, modules, and items.

Owns the authored-side of the LMS: `courses` (catalogue rows), `course_modules`
(ordered lessons inside a course), and `module_items` (every content item of
all four kinds — video|text|quiz|flashcards). A video item's async transcode
state lives on the standardized `videos` table (`app/models/videos.py`,
owner_type="module_item") rather than a table of its own — see
`services/video_service.py`.

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

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    # Organization ownership for partner-authored courses
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    submitted_for_review_at = Column(DateTime(timezone=True), nullable=True)
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

    # P1-2 (Phase 2 Stage 1, 2026-08-10) — open: anyone logged in self-enrols.
    # invite: hidden from the catalog entirely unless the caller already
    # holds an active enrollment; only an admin grant enrols. paid: self-enrol
    # starts a checkout (Stage S). Existing courses default to 'open', so
    # today's behaviour is unchanged by this column's arrival.
    access_mode = Column(String(12), nullable=False, default="open", server_default="open")
    # NULL = perpetual access once enrolled — never a 9999 sentinel (this
    # codebase's NULL-means-unrestricted convention, applied here per audit
    # §9.3(d)). Paired with enrollments.expires_at, which the access check
    # actually reads (see routers/lms/student.py::_assert_enrolled) — shipped
    # in the same stage so there's no window where expiry looks implemented
    # and silently isn't.
    access_days = Column(Integer, nullable=True)
    # Stripe Checkout (Stage S, August Build Brief Branch 4). Integer minor
    # units, matching Stripe's unit_amount/amount_total. NULL when not paid —
    # "a paid course must have a positive price" is an application check in
    # the checkout endpoint, not a DB constraint, same posture as access_mode.
    price_cents = Column(Integer, nullable=True)
    currency = Column(String(3), nullable=False, default="usd", server_default="usd")

    # Per-course certificate opt-out (2026-09-14). Defaults true — today's
    # behaviour (every finished course earns one, see
    # services/lms/certificates.py::issue_course_certificate) is unchanged
    # for existing courses. False stops a new certificate from being
    # rendered/issued for this course; it never revokes one already issued,
    # and it never blocks a learning-path certificate — course completion
    # tracking itself is untouched, only certificate issuance is skipped.
    certificate_enabled = Column(Boolean, nullable=False, default=True, server_default="true")


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

    `kind` is video|text|quiz|flashcards|attachment. `content` holds the
    authored payload for every kind (text body, quiz questions/options/
    answers, flashcard cards, attachment file reference); the video kind
    keeps its payload empty here and the real state in `module_videos`
    (async columns the worker writes — this table stays sync-authored
    only). `attachment` (2026-08-09, a PDF reader) is empty here too until
    the upload endpoint sets bucket/path/filename/size_bytes directly —
    same two-step shape as video, but no separate state table: a PDF has
    no async transcode step, so there's no state machine to track.

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
    # video|text|quiz|flashcards|attachment|mission (P5-5 — content =
    # {mission_id, variant_id?}, points at a standalone `missions` row)
    kind = Column(String(10), nullable=False)
    is_required = Column(Boolean, nullable=False, default=True)
    title = Column(String(128), nullable=True)
    # Authored payload, shapes documented in LMS_EXECUTION_PLAN.md §2.
    content = Column(JSONB, nullable=False, default=dict)


class VideoCheckpoint(Base):
    """A timeline marker authored on a video item — a note (non-blocking
    banner during `[start_seconds, end_seconds]`) or a quiz (pauses playback
    at `start_seconds`, `end_seconds` stays null since a quiz has no window,
    only a moment). Replaces the old `quiz` module-item + `mid_video_at_seconds`
    indirection (LMS_EXECUTION_PLAN.md §DISCOVERIES, 2026-08-07) — checkpoints
    now belong structurally to the video they're drawn on, matching both the
    design's own scrubber-marker mental model and how the operator actually
    wants to author them.

    `content` shape by kind: note = `{body}`; quiz = `{question_type, prompt,
    options?, correct?}` (question_type: mcq|multiselect|open). Grading is
    stateless (no ItemProgress row) — a checkpoint quiz gates *playback*, not
    module completion, so there's nothing to persist per submission.
    """

    __tablename__ = "video_checkpoints"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(
        UUID(as_uuid=True), ForeignKey("module_items.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    # Float, not Integer — checkpoints are authored to the millisecond
    # (h:m:s:ms in the UI), not just the whole second.
    start_seconds = Column(Float, nullable=False)
    end_seconds = Column(Float, nullable=True)
    # note|quiz
    kind = Column(String(10), nullable=False)
    content = Column(JSONB, nullable=False, default=dict)
