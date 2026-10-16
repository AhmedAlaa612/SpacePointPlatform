import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    Time,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base

# Association table for Many-to-Many between MentorProfile and MentorDomain
mentor_profile_domains = Table(
    "mentor_profile_domains",
    Base.metadata,
    Column(
        "mentor_id",
        UUID(as_uuid=True),
        ForeignKey("mentor_profiles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "domain_id",
        UUID(as_uuid=True),
        ForeignKey("mentor_domains.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class MentorDomain(Base):
    """Dynamic satellite & space taxonomy tags managed by Operations/Admin."""

    __tablename__ = "mentor_domains"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    category = Column(String(100), nullable=True)  # e.g. "Hardware", "Mission Design", "Software"
    is_active = Column(Boolean, nullable=False, default=True)
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class MentorProfile(Base):
    """Satellite & space mentor profile."""

    __tablename__ = "mentor_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    slug = Column(String(100), unique=True, nullable=False, index=True)
    headline = Column(String(255), nullable=True)
    company = Column(String(150), nullable=True)
    bio = Column(Text, nullable=True)
    missions_history = Column(Text, nullable=True)
    what_i_can_help_with = Column(Text, nullable=True)

    # "email" (Mode A: direct inquiries) or "calendar" (Mode B: slot bookings)
    contact_mode = Column(String(20), nullable=False, default="email")

    # Option A: Mentor's personal permanent Google Meet URL (no Google Meet API needed)
    google_meet_url = Column(String(500), nullable=True)

    # Google Calendar OAuth (for Mode B conflict checks & event insertion)
    google_refresh_token = Column(Text, nullable=True)
    google_calendar_id = Column(String(255), nullable=True)

    # Moderation & Visibility: Gated until Ops approval
    status = Column(String(20), nullable=False, default="applied")  # applied, approved, rejected, suspended
    is_active = Column(Boolean, nullable=False, default=False)
    is_published = Column(Boolean, nullable=False, default=True)
    invite_code = Column(String(50), nullable=True)
    photo_url = Column(Text, nullable=True)

    # Contact Email & Button Visibility
    contact_email = Column(String(255), nullable=True)
    show_contact_button = Column(Boolean, nullable=False, default=True)

    # Social links
    linkedin_url = Column(String(500), nullable=True)

    # Stats & Metrics
    session_duration_minutes = Column(Integer, nullable=False, default=30)
    total_completed_minutes = Column(Integer, nullable=False, default=0)
    completed_sessions_count = Column(Integer, nullable=False, default=0)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User", backref="mentor_profile", lazy="joined")
    domains = relationship(
        "MentorDomain",
        secondary=mentor_profile_domains,
        backref="mentors",
        lazy="selectin",
    )
    availabilities = relationship(
        "MentorAvailability",
        back_populates="mentor",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    bookings = relationship(
        "MentorBooking",
        back_populates="mentor",
        cascade="all, delete-orphan",
        lazy="select",
    )


class MentorAvailability(Base):
    """Weekly recurring or ad-hoc open slots defined manually in SpacePoint."""

    __tablename__ = "mentor_availabilities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mentor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("mentor_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_of_week = Column(Integer, nullable=True)  # 0=Mon, 6=Sun (NULL if specific_date is set)
    specific_date = Column(Date, nullable=True)  # Set for one-off ad-hoc dates
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    timezone = Column(String(50), nullable=False, default="UTC")
    is_active = Column(Boolean, nullable=False, default=True)

    mentor = relationship("MentorProfile", back_populates="availabilities")


class MentorBooking(Base):
    """Booked sessions (Mode B) and direct inquiries (Mode A)."""

    __tablename__ = "mentor_bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mentor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("mentor_profiles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mentee_name = Column(String(150), nullable=False)
    mentee_email = Column(String(255), nullable=False)
    topics = Column(Text, nullable=False)

    # "session" (Calendar booking) or "inquiry" (Email contact)
    booking_type = Column(String(20), nullable=False, default="session")

    scheduled_start = Column(DateTime(timezone=True), nullable=True)
    scheduled_end = Column(DateTime(timezone=True), nullable=True)

    # Stored to delete event from Google Calendar on cancellation
    google_event_id = Column(String(255), nullable=True)
    google_meet_url = Column(String(500), nullable=True)

    gateway_token = Column(String(64), unique=True, nullable=True, index=True)
    cancel_token = Column(String(64), unique=True, nullable=True, index=True)

    # "confirmed", "completed", "cancelled"
    status = Column(String(20), nullable=False, default="confirmed")

    # Attendance telemetry
    mentor_joined_at = Column(DateTime(timezone=True), nullable=True)
    mentee_joined_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    mentor = relationship("MentorProfile", back_populates="bookings")
