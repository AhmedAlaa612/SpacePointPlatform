import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class Application(Base):
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(String(50), nullable=False)          # ambassador | intern | teacher | facilitator
    status = Column(String(20), nullable=False, default="pending")  # pending | approved | rejected

    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(50), nullable=True)
    country = Column(String(100), nullable=True)
    password_hash = Column(Text, nullable=False)

    invite_code = Column(String(50), nullable=True)
    invited_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    cv_url = Column(Text, nullable=True)   # legacy fallback only — cv_path is the source of truth (A2; bucket is always "cvs")
    cv_path = Column(Text, nullable=True)
    answers = Column(JSONB, nullable=False, default=dict)

    admin_notes = Column(Text, nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
