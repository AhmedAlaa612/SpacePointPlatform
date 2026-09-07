import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class TrainingModule(Base):
    __tablename__ = "training_modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class TrainingVideo(Base):
    __tablename__ = "training_videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id = Column(UUID(as_uuid=True), ForeignKey("training_modules.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    video_path = Column(String, nullable=True)  # embed URL, or "" once superseded by an upload
    # NULL means "no generic file" — a non-null format is any uploaded file
    # other than a video (PDF, PPTX, anything), same discriminator idiom
    # LibraryResource.format already uses. A row is exactly one of: a plain
    # link (video_path set, an embed URL or any other link), an uploaded
    # video (a `videos` row, owner_type="training_video"), or an uploaded
    # generic file (format set, file_path set) — never more than one.
    format = Column(String(10), nullable=True)
    file_path = Column(String, nullable=True)  # storage path in the "library-resources" bucket
    sort_order = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class UserTrainingProgress(Base):
    __tablename__ = "user_training_progress"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    video_id = Column(UUID(as_uuid=True), ForeignKey("training_videos.id", ondelete="CASCADE"), nullable=False, index=True)
    is_completed = Column(Boolean, nullable=False, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
