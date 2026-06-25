import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class InternLetter(Base):
    """Intern confirmation/completion letters (PLAN §4.5/§8.2). `type` is a plain
    string per PLAN's own SQL (VARCHAR, not an enum) — only ever 'confirmation' or 'completion'.
    """

    __tablename__ = "intern_letters"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(50), nullable=False)
    file_url = Column(String, nullable=False)
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
