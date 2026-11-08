import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class BoothEvent(Base):
    __tablename__ = "booth_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    starts_at = Column(DateTime(timezone=True), nullable=True)
    ends_at = Column(DateTime(timezone=True), nullable=True)

    # Link to an InvitationCode (kind='student')
    invitation_code_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invitation_codes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Whether taking a photo automatically provisions an LMS student account
    auto_create_lms_account = Column(Boolean, nullable=False, default=True)

    # Custom branding/email copy (optional overrides)
    email_subject = Column(String(255), nullable=True)
    email_body_template = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    invitation_code = relationship("InvitationCode", foreign_keys=[invitation_code_id])
    photos = relationship("BoothPhoto", back_populates="event", cascade="all, delete-orphan")


class BoothPhoto(Base):
    __tablename__ = "booth_photos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("booth_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    participant_name = Column(String(255), nullable=False)
    participant_email = Column(String(255), nullable=False, index=True)

    # R2 Storage
    storage_bucket = Column(String(100), nullable=False, default="spacepoint-booth")
    storage_path = Column(String(512), nullable=False)

    satellite_id = Column(String(100), nullable=True)

    # Linked LMS student account (if created or matched)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_new_lms_user = Column(Boolean, nullable=False, default=False)

    # Email delivery tracking
    email_sent = Column(Boolean, nullable=False, default=False)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)
    email_error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    event = relationship("BoothEvent", back_populates="photos")
    user = relationship("User", foreign_keys=[user_id])
