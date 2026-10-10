import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class WebsiteFaq(Base):
    """FAQ row backing the marketing site's FAQ accordion.

    Step 4 — FAQs, Media Coverage & Monthly Newsletters: administrators
    manage these rows from the portal (/operations/website → FAQs) and the
    public site reads the active ones via GET /public/faqs without a
    redeploy.
    """

    __tablename__ = "website_faqs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category = Column(String(64), nullable=False, default="General")
    question = Column(String(255), nullable=False)
    answer = Column(Text, nullable=False)
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
