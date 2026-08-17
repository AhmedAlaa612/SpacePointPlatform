import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base
from app.models.interns.team import Team

project_teams = Table(
    "project_teams",
    Base.metadata,
    Column("project_id", UUID(as_uuid=True), ForeignKey("projects.id"), primary_key=True),
    Column("team_id", UUID(as_uuid=True), ForeignKey("teams.id"), primary_key=True),
)


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=False, default="active", server_default="active")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    creator = relationship("User", foreign_keys=[created_by])
    # 2026-08-17 — class object, not a bare "Team" string: a second,
    # unrelated Team now exists (app/models/team.py, domain-agnostic learner
    # teams), and SQLAlchemy's string relationship resolution is registry-
    # wide, not per-module — a bare "Team" string is now ambiguous.
    teams = relationship(Team, secondary=project_teams)
