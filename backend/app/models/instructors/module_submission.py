import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ENUM, UUID

from app.db.base import Base
from app.models.enums import ModuleSubmissionStatus


class ModuleSubmission(Base):
    """The actual Phase-1 PDF upload + admin review row, one per
    (user, checklist_module)."""

    __tablename__ = "module_submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    module_id = Column(UUID(as_uuid=True), ForeignKey("checklist_modules.id", ondelete="CASCADE"), nullable=False)
    file_url = Column(String, nullable=False)
    original_filename = Column(String(255), nullable=True)
    notes_text = Column(Text, nullable=True)
    status = Column(
        ENUM(ModuleSubmissionStatus, name="module_submission_status", create_type=False),
        nullable=False,
        default=ModuleSubmissionStatus.submitted,
    )
    feedback = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewer_admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
