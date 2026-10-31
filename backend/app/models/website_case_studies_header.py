from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class WebsiteCaseStudiesHeader(Base):
    """Case Studies page header configuration: hero stats counters and page trusted partners."""

    __tablename__ = "website_case_studies_header"

    id = Column(Integer, primary_key=True, default=1)
    # [{"value": "1,000+", "label": "Students Trained"}, ...]
    stats = Column(JSONB, nullable=False, default=list, server_default="[]")
    # [{"name": "HCT", "logo_url": "...", "website_url": "..."}]
    partners = Column(JSONB, nullable=False, default=list, server_default="[]")
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
