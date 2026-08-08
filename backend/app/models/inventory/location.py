import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Location(Base):
    """Somewhere kit and stock physically sits: a named place inside a city
    — "SpacePoint HQ Dubai", "Al Ain Depot" — with an optional address and
    maps link. Deliberately flat: an earlier draft had `parent_id` and a
    `kind` (main/sub/sales); both were cut because nothing *behaves*
    differently by them.

    `city_id` is the structured anchor (2026-08-08): a location is in a
    city, a city is in a country — the country of a location is therefore
    *derived* from its city, never entered separately. Backfilled where
    unambiguous by c9d1e2f3a4b5; the handful of legacy rows whose name is
    not a city name (e.g. "Main Warehouse") get fixed by ops through the
    now-required City field on the location forms.

    `country` is legacy (not-null dropped by d1e2f3a4b5c6): kept unused so
    nothing silently breaks, derived from `city_id` at every write.
    """

    __tablename__ = "locations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(128), nullable=False)
    # Legacy — ISO-3166 alpha-2 (AE, EG). Derived from `city_id` since
    # 2026-08-08; nullable only so historical rows can keep it as-is until
    # the column is dropped in a later phase. Never read outside the
    # inventory CRUD router (`_location_out` re-derives it from the city).
    country = Column(String(2), nullable=True)  # ISO-3166 alpha-2: AE, EG
    is_active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)
    # Where cohorts/sessions send instructors — the address and map link
    # belong to the place, not to whichever cohort runs there this month.
    address = Column(Text, nullable=True)
    maps_url = Column(Text, nullable=True)
    # Structured counterpart to the free-text `name` (2026-08-08) — lets
    # staffing match "instructors open to work in this city" against "the
    # city this location is actually in" by exact id, not by comparing two
    # independently hand-typed strings. Nullable/unset on existing rows;
    # ops fills it in going forward, never guessed from `name`.
    city_id = Column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
