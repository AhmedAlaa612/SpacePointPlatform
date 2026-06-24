import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class Module(Base):
    __tablename__ = "modules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    epic_id = Column(UUID(as_uuid=True), ForeignKey("epics.id"), nullable=False)
    title = Column(String, nullable=False, default="General")
    description = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    epic = relationship("Epic", back_populates="modules")
    creator = relationship("User", foreign_keys=[created_by])
    tasks = relationship("Task", back_populates="module", cascade="all, delete-orphan")
