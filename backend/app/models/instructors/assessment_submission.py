import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class AssessmentSubmission(Base):
    """Phase 2 — 10-Questions Assessment, one per user (only allowed once
    application_reviews.status == research_approved)."""

    __tablename__ = "assessment_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    file_url = Column(String, nullable=True)
    google_drive_link = Column(String, nullable=True)
    comments = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
