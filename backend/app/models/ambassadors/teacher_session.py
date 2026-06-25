import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.db.base import Base


class TeacherSession(Base):
    __tablename__ = "teacher_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    date = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(50), nullable=False, default="pending")  # pending, approved, done, rejected, cancelled
    status_note = Column(Text, nullable=True)       # reason given on cancel / reject
    material_sent = Column(Boolean, nullable=False, default=False)
    material_link = Column(Text, nullable=True)     # link the ambassador shares with the teacher
    planned_students = Column(Integer, nullable=False, default=0)
    attended_students = Column(Integer, nullable=False, default=0)
    # True while delivery points are held — lets a deletion of a done session
    # write the matching ledger reversal.
    points_awarded = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
