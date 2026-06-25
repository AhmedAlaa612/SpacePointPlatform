import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class PointsTransaction(Base):
    """Lifetime points ledger. Points only ever accrue — there are no
    'redeem' rows; reaching point thresholds unlocks Titles instead."""

    __tablename__ = "points_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ambassador_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Integer, nullable=False)
    type = Column(String(50), nullable=False, default="earn")  # always 'earn'
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
