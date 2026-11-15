import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class CertificateEmailTemplate(Base):
    """Global reusable email template for sending/publishing certificates."""

    __tablename__ = "certificate_email_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    kind = Column(String(24), nullable=False, default="individual", server_default="individual")  # individual | team | combined | profile
    subject = Column(String(255), nullable=False)
    body_html = Column(Text, nullable=False)
    is_default = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
