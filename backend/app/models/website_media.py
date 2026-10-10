import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class MediaClipping(Base):
    """Press clipping row backing the marketing site's media coverage.

    Step 4 — FAQs, Media Coverage & Monthly Newsletters: `is_arabic`
    clippings render with dir="rtl" on the public site.
    """

    __tablename__ = "media_clippings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    publisher_name = Column(String(255), nullable=False)
    article_title = Column(String(255), nullable=False)
    article_url = Column(String(512), nullable=False)
    published_date = Column(String(64), nullable=False)
    logo_url = Column(String(512), nullable=True)
    is_arabic = Column(Boolean, nullable=False, default=False)
    snippet = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
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
