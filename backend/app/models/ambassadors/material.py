import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class Material(Base):
    """Shared teaching material (slides, decks, guides) in the library.
    Uploaded by admins/ambassadors, browsable by everyone."""

    __tablename__ = "materials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    link = Column(Text, nullable=False)
    category = Column(String(100), nullable=True)  # free-form grouping, e.g. "Workshops"
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
