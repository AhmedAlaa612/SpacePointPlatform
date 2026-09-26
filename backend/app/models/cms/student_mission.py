import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class StudentMission(Base):
    """Student showcase mission model replacing hardcoded cards in student_mission.html.

    Stores student capstone research, payload engineering reports (.docx/PDF),
    and technical showcase highlights.
    """

    __tablename__ = "student_missions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_name = Column(String(255), nullable=False)
    project_title = Column(String(255), nullable=False)
    category = Column(String(128), nullable=False)  # CubeSat, CanSat, AI & Rovers, Rocketry, etc.
    description = Column(Text, nullable=False)
    docx_url = Column(String(512), nullable=True)
    photo_url = Column(String(512), nullable=True)
    metrics_json = Column(JSONB, nullable=False, default=dict, server_default="{}")
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
