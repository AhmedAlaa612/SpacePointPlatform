import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.enums import WorkStatus
from app.models.interns.team import Team


class Epic(Base):
    __tablename__ = "epics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        ENUM(WorkStatus, name="work_status", create_type=False),
        nullable=False,
        default=WorkStatus.todo,
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    project = relationship("Project")
    # 2026-08-17 — class object, not a bare "Team" string: see the matching
    # comment in interns/project.py for why (a second, unrelated Team now
    # exists at app/models/team.py, making the bare string ambiguous).
    team = relationship(Team)
    creator = relationship("User", foreign_keys=[created_by])
    modules = relationship("Module", back_populates="epic", cascade="all, delete-orphan")
