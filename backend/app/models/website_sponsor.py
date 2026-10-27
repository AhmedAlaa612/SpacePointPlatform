import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base

#: Tiers the marketing site groups sponsors by. Kept as plain strings (not
#: a PG ENUM) so new showcase tiers never need a DB migration.
SPONSOR_TIERS = ("client", "partner", "supporter", "academic", "industry_leader")


class WebsiteSponsor(Base):
    """Partner/client logo row backing the marketing site's showcase.

    Step 3 — Partners, Clients & Industry Leaders Showcase: administrators
    manage these rows from the portal (/operations/website → Partners &
    Clients) and the public site reads the active ones via
    GET /public/sponsors without a redeploy.
    """

    __tablename__ = "sponsors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    logo_url = Column(String(512), nullable=False)
    logo_hover_url = Column(String(512), nullable=True)
    website_url = Column(String(512), nullable=True)
    tier = Column(String(32), nullable=False, default="partner")
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
