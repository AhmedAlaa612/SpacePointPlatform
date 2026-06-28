import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Numeric, String, Table, Text
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.enums import WorkStatus

task_assignees = Table(
    "task_assignees",
    Base.metadata,
    Column("task_id", UUID(as_uuid=True), ForeignKey("tasks.id"), primary_key=True),
    Column("user_id", UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    module_id = Column(UUID(as_uuid=True), ForeignKey("modules.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        ENUM(WorkStatus, name="work_status", create_type=False),
        nullable=False,
        default=WorkStatus.todo,
    )
    due_date = Column(DateTime(timezone=True), nullable=True)
    expected_time = Column(Numeric(6, 2), nullable=True)
    actual_time = Column(Numeric(6, 2), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    module = relationship("Module", back_populates="tasks")
    creator = relationship("User", foreign_keys=[created_by])
    assignees = relationship("User", secondary=task_assignees)
    submissions = relationship("TaskSubmission", back_populates="task", cascade="all, delete-orphan")
    mind_map_note = relationship(
        "TaskMindMapNote", back_populates="task", uselist=False, cascade="all, delete-orphan"
    )
