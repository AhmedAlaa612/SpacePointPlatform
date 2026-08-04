"""LMS enrollment domain (LM1-1) — the access gate and per-student progress.

`enrollments` is the single access gate for playing a course (LMS D8): a
student may read a course's content iff there is an active row here. `source`
records how the row started (self|ops|registration); `program_id` and
`registration_id` are provenance pointers, not live membership — if the same
student ends up in a course through two programs, `UNIQUE(user_id, course_id)`
keeps one row and only the first path is recorded (§2 note).

`item_progress` is one row per student per item. Completion is DERIVED from
these rows (module done = every mandatory item completed), never stored, so
there is no flag to go stale.

Both tables CASCADE on user delete — a deleted student's enrollments and
progress vanish with them. Progress is worthless without the student; this is
the deliberate inverse of inventory custody (which preserves history).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Enrollment(Base):
    """A student's access to one course — the row everything in the player and
    the instructor view checks first.

    `status` is active|inactive: a cancelled registration flips the enrollments
    that started from it to inactive; reinstatement flips them back (LM1-7).
    `program_id`/`registration_id` are SET NULL on their parent's deletion — the
    enrollment survives as self-source history rather than disappearing with the
    provenance it started from.
    """

    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_enrollments_user_course"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    # self|ops|registration
    source = Column(String(12), nullable=False, default="self")
    # Provenance only — how this enrollment STARTED (§2). Never live membership.
    program_id = Column(
        UUID(as_uuid=True), ForeignKey("programs.id", ondelete="SET NULL"), nullable=True
    )
    registration_id = Column(
        UUID(as_uuid=True), ForeignKey("registrations.id", ondelete="SET NULL"), nullable=True
    )
    # active|inactive
    status = Column(String(10), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ItemProgress(Base):
    """One row per student per item — the raw material completion is derived from.

    `status` is not_started|in_progress|completed|skipped. `quiz_attempts` and
    `best_score` belong to quiz items; `completed_at` is set once when the item
    flips to completed (not updated on retries). `updated_at` is written by
    every action (video-watched, text-viewed, quiz-attempt). Skipped optional
    items count as done for unlock purposes, exactly as the plan says.
    """

    __tablename__ = "item_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_item_progress_user_item"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(
        UUID(as_uuid=True), ForeignKey("module_items.id", ondelete="CASCADE"), nullable=False
    )
    # not_started|in_progress|completed|skipped
    status = Column(String(12), nullable=False, default="not_started")
    quiz_attempts = Column(Integer, nullable=False, default=0)
    best_score = Column(Numeric(5, 2), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)