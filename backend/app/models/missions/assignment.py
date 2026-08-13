"""Mission assignment (2026-08-12) — the mission-side equivalent of
`Enrollment` (`models/lms/enrollment.py`). Missions had no grant table at
all before this: `MissionAttempt` is a run record, not access, so there was
no way to represent "ops put this staff member on this mission" the way
enrollment already represents it for courses.

Mirrors `Enrollment`'s shape deliberately — same `status` (active|inactive,
soft-revoke, never delete), same `granted_by` (SET NULL so the row survives
the granter's account being removed). Bookkeeping only for now: it does not
gate `MissionAttempt` creation (`access_mode` still does that) — whether it
should is an open question the assignment endpoints' docstrings flag rather
than guess at.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class MissionAssignment(Base):
    __tablename__ = "mission_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "mission_id", name="uq_mission_assignments_user_mission"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False)
    # ops is the only source today — unlike enrollments there is no
    # self/registration path onto a mission assignment.
    source = Column(String(12), nullable=False, default="ops")
    # active|inactive
    status = Column(String(10), nullable=False, default="active")
    granted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
