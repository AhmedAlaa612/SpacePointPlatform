import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class WebsiteLabProject(Base):
    """R&D project card backing labs.spacepoint.ae (Step 7)."""

    __tablename__ = "website_labs_projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    slug = Column(String(128), nullable=False, unique=True, index=True)
    badges = Column(JSONB, nullable=False, default=list, server_default="[]")
    description = Column(Text, nullable=False)
    project_url = Column(String(512), nullable=False, default="/miura-ori")
    cta_label = Column(String(128), nullable=False, default="Launch Project →")
    cover_image_url = Column(String(512), nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
