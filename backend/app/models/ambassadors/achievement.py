import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class Achievement(Base):
    """A milestone badge an ambassador has earned (e.g. first_lead,
    ten_sessions). Distinct from Titles: badges reward specific actions,
    titles reward cumulative points."""

    __tablename__ = "achievements"
    __table_args__ = (UniqueConstraint("ambassador_id", "code", name="uq_achievement_per_user"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ambassador_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code = Column(String(50), nullable=False)   # matches a definition in services/achievements.py
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
