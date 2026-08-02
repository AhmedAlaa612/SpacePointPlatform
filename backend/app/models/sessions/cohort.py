import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Cohort(Base):
    """One actual run of a program — real dates, a location, a capacity, and
    the registrations that go with it. status tracks the registration
    lifecycle. Staffing (unstaffed|open_call|staffed) lives on Session, not
    here (moved 2026-07-24, W4) — assignment is per-session, so a cohort
    with several sessions can be partly staffed; there's no single cohort-
    level staffing state to store."""

    __tablename__ = "cohorts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    starts_on = Column(Date, nullable=True)
    ends_on = Column(Date, nullable=True)
    # Legacy free text — superseded by location_id (2026-08-01), kept
    # unused rather than dropped so nothing already typed here is lost.
    location = Column(String(128), nullable=True)
    location_map_url = Column(Text, nullable=True)
    # The cohort's venue — the same `locations` table kits and stock already
    # use. A session can override this for the rare one-off that meets
    # somewhere else (see Session.location_id).
    location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True)
    # Which warehouse at that location equipment is picked from (2026-08-01).
    # NULL = resolve it: the location's only warehouse if it has exactly one,
    # otherwise ops has to say which shelf. Location and warehouse are kept
    # separate on purpose — a location can hold several warehouses, so
    # "Dubai" alone was never precise enough to pull stock from. A session
    # can override this the same way it overrides location_id.
    warehouse_id = Column(UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True)
    capacity = Column(Integer, nullable=True)
    # I5-2. NULL = inherit from the program. See Program.duration_hours.
    duration_hours = Column(Numeric(5, 2), nullable=True)
    lead_instructor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # planned|registration_open|running|completed|cancelled
    # NOTE: VARCHAR(24), not (16) — 'registration_open' itself is 17 chars.
    status = Column(String(24), nullable=False, default="planned")

    madar_invitation_batch = Column(String(64), nullable=True)
    notes = Column(Text, nullable=True)

    # B2B private cohort (V2 R1-2 delta)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)
    visibility = Column(String(12), nullable=False, default="public")  # public|private

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
