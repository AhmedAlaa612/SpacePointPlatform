import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class ApplicationQuestion(Base):
    """Admin-configurable custom question shown on the public /apply/{role} form.

    `audience` is the role the question applies to (ambassador / intern /
    teacher / facilitator). Soft-deleted via is_active so historical answers
    keep their question reference.
    """

    __tablename__ = "apply_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audience = Column(String(50), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(20), nullable=False, default="text")  # text | number | radio | multiple_choice
    required = Column(Boolean, nullable=False, default=True)
    options = Column(JSONB, nullable=False, default=list)  # choices for radio / multiple_choice
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
