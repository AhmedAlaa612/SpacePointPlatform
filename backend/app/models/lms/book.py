"""LMS Interactive Books domain — catalog metadata, access gates, cross-device progress,
and structured exercise/notebook response tracking.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class LmsBook(Base):
    """An interactive HTML book bundle (stored in R2/storage) with LMS access control and outline."""

    __tablename__ = "lms_books"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(128), nullable=False, unique=True, index=True)
    title = Column(String(200), nullable=False)
    title_ar = Column(String(200), nullable=True)
    subtitle = Column(String(300), nullable=True)
    description = Column(Text, nullable=True)
    author_name = Column(String(160), nullable=True)

    cover_bucket = Column(String(64), nullable=True)
    cover_path = Column(String(512), nullable=True)

    languages = Column(JSONB, nullable=False, default=lambda: ["en"])
    bundle_version = Column(Integer, nullable=False, default=0, server_default="0")
    bundle_entry = Column(String(255), nullable=False, default="index.html", server_default="index.html")
    bundle_storage_backend = Column(String(16), nullable=True)
    bundle_size_bytes = Column(Integer, nullable=True)

    outline = Column(JSONB, nullable=False, default=list)
    profiles = Column(JSONB, nullable=False, default=list)
    default_profile = Column(String(32), nullable=False, default="all", server_default="all")

    # open | invite | paid
    access_mode = Column(String(12), nullable=False, default="open", server_default="open")
    access_days = Column(Integer, nullable=True)
    price_cents = Column(Integer, nullable=True)
    currency = Column(String(3), nullable=False, default="usd", server_default="usd")

    is_published = Column(Boolean, nullable=False, default=False, server_default="false")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class LmsBookEdition(Base):
    """Named chapter-subset edition of an `LmsBook`, created by SpacePoint staff or an organization."""

    __tablename__ = "lms_book_editions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id = Column(UUID(as_uuid=True), ForeignKey("lms_books.id", ondelete="CASCADE"), nullable=False, index=True)
    organization_id = Column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(200), nullable=False)
    title_ar = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    chapter_keys = Column(JSONB, nullable=False, default=list, server_default="[]")
    default_lang = Column(String(8), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class LmsBookEnrollment(Base):
    """Per-user access gate for a book (granted via self-enroll, purchase, invite code, program, or ops)."""

    __tablename__ = "lms_book_enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_lms_book_enrollments_user_book"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    book_id = Column(UUID(as_uuid=True), ForeignKey("lms_books.id", ondelete="CASCADE"), nullable=False, index=True)
    book_edition_id = Column(
        UUID(as_uuid=True), ForeignKey("lms_book_editions.id", ondelete="SET NULL"), nullable=True,
    )
    # self | ops | program | purchase | invite_code
    source = Column(String(16), nullable=False, default="self", server_default="self")
    # active | inactive
    status = Column(String(10), nullable=False, default="active", server_default="active")
    granted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    purchase_id = Column(UUID(as_uuid=True), ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class LmsBookProgress(Base):
    """Cross-device reading position, visited spreads, stars, and raw store snapshot for a student's book."""

    __tablename__ = "lms_book_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_lms_book_progress_user_book"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    book_id = Column(UUID(as_uuid=True), ForeignKey("lms_books.id", ondelete="CASCADE"), nullable=False, index=True)
    current_spread = Column(String(128), nullable=True)
    current_chapter = Column(String(64), nullable=True)
    active_profile = Column(String(32), nullable=True)
    visited_spreads = Column(JSONB, nullable=False, default=list)
    stars = Column(JSONB, nullable=False, default=dict)
    stars_earned = Column(Integer, nullable=False, default=0, server_default="0")
    stars_possible = Column(Integer, nullable=False, default=0, server_default="0")
    completion_pct = Column(Integer, nullable=False, default=0, server_default="0")
    raw_state = Column(JSONB, nullable=False, default=dict)
    last_read_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class LmsBookExerciseResponse(Base):
    """Structured answer/score for a game, quiz, your-turn check, notebook prompt, or lab table inside a book."""

    __tablename__ = "lms_book_exercise_responses"
    __table_args__ = (
        UniqueConstraint("user_id", "book_id", "exercise_key", name="uq_lms_book_exercise_user_book_key"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    book_id = Column(UUID(as_uuid=True), ForeignKey("lms_books.id", ondelete="CASCADE"), nullable=False, index=True)
    chapter_key = Column(String(64), nullable=True, index=True)
    exercise_key = Column(String(160), nullable=False)
    # game | quiz | your_turn | notebook | lab
    exercise_type = Column(String(24), nullable=False)
    prompt_text = Column(Text, nullable=True)
    answer_json = Column(JSONB, nullable=False, default=dict)
    is_correct = Column(Boolean, nullable=True)
    score_stars = Column(Integer, nullable=True)
    max_stars = Column(Integer, nullable=True)
    attempts = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
