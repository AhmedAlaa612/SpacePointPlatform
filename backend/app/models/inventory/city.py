import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class City(Base):
    """A small, admin-configurable list of cities the org actually operates
    in (2026-08-08) — seeded with the UAE cities the instructor-apply form
    already offered, growable by ops as new regions open up.

    The structural counterpart to two previously-free-text fields:
    `Location.city_id` (where a location actually sits) and
    `ApplicantProfile.deliver_city_ids`/`users.city_id` (which cities a
    person is in/open to work in) — both now reference the same rows here,
    so "does this instructor cover this location's city" is an exact ID
    match instead of comparing two independently hand-typed strings.
    """

    __tablename__ = "cities"
    __table_args__ = (
        UniqueConstraint("country", "name", name="uq_cities_country_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(80), nullable=False)
    country = Column(String(2), nullable=False)  # ISO-3166 alpha-2: AE, EG
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
