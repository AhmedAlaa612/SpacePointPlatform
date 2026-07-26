import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class Activity(Base):
    """A live-quiz-style game a facilitator builds (schema only for now — the
    engine that runs it live lands in G13-1/G14-1, week 13-14). activity_type
    leaves room for non-quiz game types later without a new table."""

    __tablename__ = "activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_type = Column(String(16), nullable=False, default="quiz")
    title = Column(String(255), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(16), nullable=False, default="draft")  # draft|published
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ActivityVersion(Base):
    """A specific edit of an activity — questions/answers/timing live in
    `definition`. Versioned so an in-progress live session keeps using the
    version it started with even if the facilitator edits afterward."""

    __tablename__ = "activity_versions"
    __table_args__ = (
        UniqueConstraint("activity_id", "version", name="uq_activity_version"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_id = Column(UUID(as_uuid=True), ForeignKey("activities.id", ondelete="CASCADE"), nullable=False)
    version = Column(Integer, nullable=False)
    definition = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ActivityAssignment(Base):
    """Attaches one activity version to a program (every cohort of it) or a
    single cohort — never both, never neither."""

    __tablename__ = "activity_assignments"
    __table_args__ = (
        CheckConstraint(
            "(program_id IS NULL) != (cohort_id IS NULL)",
            name="ck_activity_assignment_exactly_one_target",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_version_id = Column(UUID(as_uuid=True), ForeignKey("activity_versions.id", ondelete="CASCADE"), nullable=False)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=True)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
