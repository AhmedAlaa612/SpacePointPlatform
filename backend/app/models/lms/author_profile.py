import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class LmsAuthorProfile(Base):
    """Author permissions profile for LMS authors (partners/contributors).
    
    `can_publish`: if True, author can publish/unpublish their courses & paths directly.
                   if False, courses/paths stay in draft / require admin review.
    `scope_all`: if True, author can see/edit all platform courses/paths.
                 if False (default), author only sees/edits courses/paths where created_by == user.id.
    """

    __tablename__ = "lms_author_profiles"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    can_publish = Column(Boolean, nullable=False, default=False, server_default="false")
    scope_all = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
