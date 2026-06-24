import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.enums import SubmissionStatus


class TaskSubmission(Base):
    __tablename__ = "task_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False)
    submitted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    link = Column(String, nullable=False)
    note = Column(Text, nullable=True)
    status = Column(
        ENUM(SubmissionStatus, name="submission_status", create_type=False),
        nullable=False,
        default=SubmissionStatus.submitted,
    )
    score = Column(Integer, nullable=True)
    review_comment = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    task = relationship("Task", back_populates="submissions")
    submitter = relationship("User", foreign_keys=[submitted_by])
