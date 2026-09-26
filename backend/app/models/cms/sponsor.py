import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Sponsor(Base):
    """Sponsor/partner record replacing hardcoded HTML marquee logos.

    Tier classifications:
    - client: Organizations that hire SpacePoint for custom missions/workshops
    - partner: Strategic technical & operational partners
    - supporter: Government, patron, and ecosystem supporters
    - academic: Universities, schools, and STEM educational institutes
    """

    __tablename__ = "sponsors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    logo_url = Column(String(512), nullable=False)
    website_url = Column(String(512), nullable=True)
    tier = Column(String(64), nullable=False, default="partner", index=True)
    display_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
