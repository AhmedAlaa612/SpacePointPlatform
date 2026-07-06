import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY

from app.db.base import Base


class DocumentTemplate(Base):
    """Database model for customizable document templates (PLAN §4.5/§8.2).
    Allows admins to change the body text and background templates for
    certificates, completion/confirmation letters, and recommendation letters.
    A single template can be available to multiple roles (e.g. both 'intern'
    and 'instructor') to avoid duplicate template records.
    """

    __tablename__ = "document_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(50), nullable=False, unique=True, index=True)
    name = Column(String(255), nullable=False)
    roles = Column(ARRAY(String), nullable=False, default=list)  # e.g. ["intern", "instructor"]
    body_text = Column(Text, nullable=True)
    template_file_url = Column(String(512), nullable=True)   # legacy fallback only — template_file_path is the source of truth (A2)
    template_file_path = Column(String(512), nullable=True)  # path inside the "library-resources" bucket
    type = Column(String(20), nullable=False, default="letter")   # 'letter' | 'certificate' — drives the renderer
    is_system = Column(Boolean, nullable=False, default=False)     # seeded + non-deletable (e.g. workshop_delivery)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

