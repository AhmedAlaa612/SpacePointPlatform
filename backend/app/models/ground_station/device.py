"""A physical ground-station rig (radio + optional camera) the on-site
agent (`ops/ground-station/agent/`) authenticates as. `secret_hash` uses the
same `get_password_hash`/`verify_password` helpers as user passwords
(`app/core/security.py`) — never stored or shipped in plaintext, only handed
to whoever configures the agent's local `.env` at registration time.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class GroundStationDevice(Base):
    __tablename__ = "ground_station_devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label = Column(String(128), nullable=False)
    secret_hash = Column(String(255), nullable=False)
    # online|offline — flipped by the ingest endpoints on each successful call.
    status = Column(String(8), nullable=False, default="offline", server_default="offline")
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
