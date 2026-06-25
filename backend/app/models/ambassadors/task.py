import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class AmbassadorTask(Base):
    __tablename__ = "ambassador_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True)
    # pending, accepted, submitted, approved, rejected, edit_requested
    status = Column(String(50), nullable=False, default="pending")
    points_reward = Column(Integer, nullable=False, default=0)
    edit_notes = Column(Text, nullable=True)        # reviewer's revision notes
    submission = Column(Text, nullable=True)        # ambassador's submitted work (link / notes)
    # True while reward points are held by the assignee — prevents re-awarding on
    # approve → revert → approve cycles (mirrors leads.points_awarded).
    points_awarded = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
