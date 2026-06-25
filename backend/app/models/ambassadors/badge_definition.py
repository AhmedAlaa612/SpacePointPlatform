import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class BadgeDefinition(Base):
    """Admin-configurable milestone badge. Unlocked when an ambassador's
    `criteria_type` metric reaches `threshold`."""

    __tablename__ = "badge_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False)  # stable slug used in `achievements`
    label = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    icon = Column(String(50), nullable=True)
    # one of: converted_leads, active_teachers, sessions_done, students_reached, lifetime_points
    criteria_type = Column(String(50), nullable=False)
    audience = Column(String(20), nullable=False, default="ambassador")  # ambassador | teacher
    threshold = Column(Integer, nullable=False, default=1)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
