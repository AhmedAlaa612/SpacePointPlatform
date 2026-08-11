"""Mission-manager scoped permission (7B-7, Missions Phase 2B, 2026-08-12) —
D7's payoff for an approved intern proposal: the intern gets to see how
their mission is doing and review its submissions, without becoming
ops/facilitator generally. Many-to-many on purpose — a mission can have
co-authors, same reasoning `mission_teams` already has for its roster.

Layered on top of the existing role checks, not replacing them: staff
(`require_lms_content`'s population) can always manage any mission, same as
everywhere else in this codebase. `services/missions/authorization.py` is
where that "staff OR a row here" rule actually lives.

Deliberately does NOT grant editing a published mission's live thresholds —
that stays frozen until the mission goes back to `draft` (D9), protecting
the same class of bug already fixed once for Madar (F2/F4: editing live
grading criteria retroactively changes already-graded work).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class MissionManager(Base):
    __tablename__ = "mission_managers"
    __table_args__ = (
        PrimaryKeyConstraint("mission_id", "user_id", name="pk_mission_managers"),
    )

    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    granted_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
