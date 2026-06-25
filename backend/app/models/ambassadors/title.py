import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class Title(Base):
    """Admin-configurable rank. Reaching `min_points` (lifetime) unlocks it."""

    __tablename__ = "titles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    min_points = Column(Integer, nullable=False, default=0)
    icon = Column(String(50), nullable=True)   # lucide icon name, e.g. "Rocket"
    color = Column(String(20), nullable=True)  # hex, e.g. "#a880ff"
    audience = Column(String(20), nullable=False, default="ambassador")  # ambassador | teacher
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
