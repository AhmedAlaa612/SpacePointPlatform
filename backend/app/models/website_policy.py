import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class WebsitePolicy(Base):
    """Public policy or legal document on the website (e.g. Privacy, Code of Conduct).

    Managed from Portal (Ops -> Website -> Policies) via /admin/website/policies.
    Public site reads active policies via /public/website/policies without redeploying.
    """

    __tablename__ = "website_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(128), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=False)
    eyebrow = Column(String(128), nullable=True)  # e.g. "Corporate Governance & Sustainability"
    meta = Column(String(255), nullable=True)  # e.g. "Approved by Abdullah AlSalmani, Co-Founder & CEO · 25 October 2026"
    summary = Column(Text, nullable=True)
    content_html = Column(Text, nullable=False)
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    show_in_footer = Column(Boolean, nullable=False, default=True)
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
