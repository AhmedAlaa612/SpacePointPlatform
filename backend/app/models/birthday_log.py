import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class BirthdayEmailLog(Base):
    __tablename__ = "birthday_email_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    sent_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    sent_at_year = Column(Integer, nullable=False, default=lambda: datetime.now(timezone.utc).year, index=True)
    birth_year_referenced = Column(Integer, nullable=True)  # e.g. 2018 NASA image chosen for their 2026 birthday
    nasa_image_url = Column(Text, nullable=True)
    nasa_title = Column(String(512), nullable=True)
    nasa_explanation = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="sent")  # sent | failed | skipped
    error_message = Column(Text, nullable=True)

    user = relationship("User", backref="birthday_email_logs", lazy="joined")

    __table_args__ = (
        Index("ix_birthday_email_logs_user_year", "user_id", "sent_at_year"),
        Index("ix_birthday_email_logs_status", "status"),
        Index("ix_birthday_email_logs_sent_at", "sent_at"),
    )
