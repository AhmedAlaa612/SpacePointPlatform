import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


def _timestamps():
    now = lambda: datetime.now(timezone.utc)  # noqa: E731
    return (
        Column(DateTime(timezone=True), nullable=False, default=now),
        Column(DateTime(timezone=True), nullable=False, default=now, onupdate=now),
    )


class TeamMember(Base):
    """Core team profile backing spacepoint.ae/team (Step 6).

    The table is `website_team_members`, not `team_members`: the legacy
    interns association table already claims `team_members` on this
    metadata, so the website showcase takes the prefixed name like its
    `website_ambassadors` / `website_alumni` siblings.
    """

    __tablename__ = "website_team_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    role = Column(String(128), nullable=False)
    department = Column(String(64), nullable=False, default="Engineering")
    bio = Column(Text, nullable=True)
    photo_url = Column(String(512), nullable=False)
    linkedin_url = Column(String(512), nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at, updated_at = _timestamps()


class WebsiteAmbassador(Base):
    """Ambassador profile backing spacepoint.ae/ambassadors (Step 6)."""

    __tablename__ = "website_ambassadors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    university = Column(String(255), nullable=False)
    major = Column(String(128), nullable=True)
    year = Column(String(32), nullable=True)
    bio = Column(Text, nullable=True)
    photo_url = Column(String(512), nullable=False)
    badge = Column(String(64), nullable=True)
    linkedin_url = Column(String(512), nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at, updated_at = _timestamps()


class WebsiteAlumni(Base):
    """Alumni placement card backing spacepoint.ae/alumni (Step 6)."""

    __tablename__ = "website_alumni"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    program_completed = Column(String(128), nullable=False)
    current_role = Column(String(255), nullable=False)
    testimonial = Column(Text, nullable=True)
    photo_url = Column(String(512), nullable=False)
    linkedin_url = Column(String(512), nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at, updated_at = _timestamps()


class StudentMission(Base):
    """Student research project backing spacepoint.ae/student-missions (Step 6)."""

    __tablename__ = "student_missions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_name = Column(String(255), nullable=False)
    project_title = Column(String(255), nullable=False)
    category = Column(String(128), nullable=False)
    description = Column(Text, nullable=False)
    docx_url = Column(String(512), nullable=True)
    photo_url = Column(String(512), nullable=True)
    metrics_json = Column(JSONB, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at, updated_at = _timestamps()
