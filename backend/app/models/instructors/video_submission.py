import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ENUM, UUID

from app.db.base import Base
from app.models.enums import VideoSubmissionStatus


class VideoSubmission(Base):
    """3 rows auto-created per applicant on signup (video_no 1-3)."""

    __tablename__ = "video_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    video_no = Column(Integer, nullable=False)  # 1-3
    youtube_url = Column(String, nullable=True)
    summary_text = Column(String, nullable=True)
    word_count = Column(Integer, nullable=False, default=0)
    status = Column(
        ENUM(VideoSubmissionStatus, name="instructor_video_status", create_type=False),
        nullable=False,
        default=VideoSubmissionStatus.draft,
    )
    submitted_at = Column(DateTime(timezone=True), nullable=True)
