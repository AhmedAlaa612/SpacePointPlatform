import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ENUM, UUID

from app.db.base import Base
from app.models.enums import VideoSubmissionStatus


class VideoSubmission(Base):
    """One row per applicant per Phase 1 video (video_no 1..N). Rows are
    auto-created on signup, one per video the facilitator has configured at
    that moment (see services/instructors/application_videos.py) — N was
    fixed at 3 originally, but the facilitator's Video Links count is
    editable (2026-09), so this is a snapshot of whatever count was
    current at signup, not a fixed 1-3."""

    __tablename__ = "video_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    video_no = Column(Integer, nullable=False)
    youtube_url = Column(String, nullable=True)
    summary_text = Column(String, nullable=True)
    word_count = Column(Integer, nullable=False, default=0)
    status = Column(
        ENUM(VideoSubmissionStatus, name="instructor_video_status", create_type=False),
        nullable=False,
        default=VideoSubmissionStatus.draft,
    )
    submitted_at = Column(DateTime(timezone=True), nullable=True)
