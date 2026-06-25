import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class Lead(Base):
    __tablename__ = "leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ambassador_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    contact_name = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)  # B2B only; B2C leads are individuals
    type = Column(String(50), nullable=False)  # 'B2B', 'distributor'
    status = Column(String(50), nullable=False, default="submitted")  # submitted, in review, converted, closed
    notes = Column(Text, nullable=True)
    # True once conversion points have been awarded — prevents re-awarding when
    # the status toggles converted → closed → converted again.
    points_awarded = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
