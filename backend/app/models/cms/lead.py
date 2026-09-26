import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class WebsiteLead(Base):
    """Website lead and submission model replacing Google Form submissions.

    Captures:
    - Workshop & School Bookings (`lead_type="workshop_booking"`)
    - Newsletter Subscriptions (`lead_type="newsletter"`)
    - General Inquiries (`lead_type="inquiry"`)
    """

    __tablename__ = "website_leads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_type = Column(String(64), nullable=False, index=True)  # workshop_booking | newsletter | inquiry
    contact_name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=False, index=True)
    phone = Column(String(64), nullable=True)
    organization_name = Column(String(255), nullable=True)
    program_interest = Column(String(255), nullable=True)
    details = Column(JSONB, nullable=False, default=dict, server_default="{}")

    # Pipeline status: new | contacted | converted | archived
    status = Column(String(32), nullable=False, default="new", index=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
