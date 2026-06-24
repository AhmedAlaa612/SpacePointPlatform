import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class MindMapLayout(Base):
    """Stores ReactFlow node positions per epic so the map doesn't re-arrange on reload."""

    __tablename__ = "mind_map_layouts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    epic_id = Column(UUID(as_uuid=True), ForeignKey("epics.id"), nullable=False, unique=True)
    layout = Column(JSONB, nullable=False, default=dict)  # { "nodeId": { "x": 0, "y": 0 } }
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    epic = relationship("Epic")


class TaskMindMapNote(Base):
    """Intern's approach/logic note for their task node on the epic mind map."""

    __tablename__ = "task_mind_map_notes"

    task_id = Column(UUID(as_uuid=True), ForeignKey("tasks.id"), primary_key=True)
    note = Column(Text, nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    task = relationship("Task", back_populates="mind_map_note")
    updater = relationship("User", foreign_keys=[updated_by])
