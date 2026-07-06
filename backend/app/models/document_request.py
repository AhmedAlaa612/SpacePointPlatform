import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class DocumentRequest(Base):
    """Document request by a user to the admin (e.g. recommendation letter, certificate)."""

    __tablename__ = "document_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False)  # 'recommendation_letter', 'confirmation_letter', 'completion_letter', 'certificate'
    status = Column(String(50), nullable=False, default="pending")  # 'pending', 'approved', 'rejected'
    requested_role = Column(String(50), nullable=True)  # role the user was acting as when they submitted (e.g. 'instructor')
    notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)
    file_url = Column(Text, nullable=True)  # legacy fallback only — bucket/file_path are the source of truth (A2)
    bucket = Column(String(100), nullable=True)
    file_path = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
