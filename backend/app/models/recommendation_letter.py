import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class RecommendationLetter(Base):
    """Shared, any-role recommendation letter (PLAN §4.5/§8.2). Admin-only, manual trigger."""

    __tablename__ = "recommendation_letters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    signatory_name = Column(String(255), nullable=False)
    signatory_title = Column(String(255), nullable=False)
    file_url = Column(String, nullable=False)
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
