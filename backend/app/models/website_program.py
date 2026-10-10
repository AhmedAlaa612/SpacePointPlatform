import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class WebsiteProgram(Base):
    """Flagship program row backing the marketing site's Programs page.

    Step 2 — Core Programs & AED Pricing Management: administrators edit
    these rows from the portal (/operations/website → Programs & Pricing)
    and the public site reads the published ones via
    GET /public/website/programs without a redeploy.
    """

    __tablename__ = "website_programs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(64), nullable=False, unique=True, index=True)
    title = Column(String(128), nullable=False)
    tagline = Column(String(255), nullable=True)
    category = Column(String(64), nullable=False, default="Aerospace Engineering")
    level = Column(String(64), nullable=False, default="Intermediate")
    duration = Column(String(64), nullable=False, default="4 Weeks")
    price_aed = Column(Integer, nullable=False)
    compare_at_price_aed = Column(Integer, nullable=True)
    badge_text = Column(String(64), nullable=True)
    features_list = Column(JSONB, nullable=False, default=list, server_default="[]")
    syllabus_url = Column(String(512), nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    is_published = Column(Boolean, nullable=False, default=True)
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
