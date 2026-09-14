"""A physical ground-station rig (radio + optional camera). Ownership
(2026-09-14, "private to the team + ops" rework): a rig is now provisioned
per `MissionAttempt` — a solo student or a team's own hardware, visible
only to that attempt's owner(s) and staff (see `services/ground_station/
access.py`). `secret_hash` is a leftover from the original device-secret
scheme; ingest no longer checks it (operator directive: no auth on ingest,
the page itself is already private) — kept only so existing rows don't
need a migration, never read on the ingest path anymore.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class GroundStationDevice(Base):
    __tablename__ = "ground_station_devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label = Column(String(128), nullable=False)
    secret_hash = Column(String(255), nullable=True)
    # Which mission attempt (solo or team) owns this rig — NULL for a
    # staff-provisioned shared/orphan device with no student owner (visible
    # to staff only). One rig per attempt (unique).
    mission_attempt_id = Column(
        UUID(as_uuid=True), ForeignKey("mission_attempts.id", ondelete="CASCADE"),
        nullable=True, unique=True,
    )
    # online|offline — flipped by the ingest endpoints on each successful call.
    status = Column(String(8), nullable=False, default="offline", server_default="offline")
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
