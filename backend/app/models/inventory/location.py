import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Location(Base):
    """Somewhere kit and stock physically sits: Main UAE, Dubai, Abu Dhabi,
    Al Ain, Egypt — and, later, a sales warehouse if the shop ever happens.

    Deliberately flat. An earlier draft had `parent_id` and a `kind`
    (main/sub/sales); both were cut because nothing *behaves* differently by
    them — stock does not roll up a hierarchy and no rule reads the kind. It
    is five rows. `country` stays because it is real: it decides what counts
    as a cross-border transfer (which is the one movement that needs
    approval) and, later, which currency a purchase defaults to.
    """

    __tablename__ = "locations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(128), nullable=False)
    country = Column(String(2), nullable=False)  # ISO-3166 alpha-2: AE, EG
    is_active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)
    # Where cohorts/sessions send instructors — the address and map link
    # belong to the place, not to whichever cohort runs there this month.
    address = Column(Text, nullable=True)
    maps_url = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
