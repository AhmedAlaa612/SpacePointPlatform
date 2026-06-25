import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from app.db.base import Base


class ApplicationQuestion(Base):
    __tablename__ = "application_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_text = Column(String(500), nullable=False)
    question_type = Column(String(50), nullable=False)  # text, number, radio, multiple_choice
    required = Column(Boolean, nullable=False, default=True)
    order = Column(Integer, nullable=False, default=0)
    options = Column(ARRAY(String), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime(timezone=True), nullable=True)
