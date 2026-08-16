"""Per-cohort, per-mission, per-step unlock state (2026-08-17) — a revival
of the dropped `design_step_gates` table (migration `94eaeb5ddbde`, dropped
by `d4a1c07e5b32` during Design v2 with the stated reason "instructors stay
out of the mission entirely"). That table shipped with no UI to ever flip
it, sat permanently unlocked, and was removed as dead weight. The operator
has now explicitly reversed that call — this time the schema and the UI
that uses it ship in the same change, on purpose, so it can't go inert
again.

`mission_id` joins the key vs. the original `(cohort_id, step_key)` shape,
since a cohort can in principle run more than one gated mission and gate
state shouldn't collide across them. A missing row means locked — same
"absence is the safe default" rule the original table used. Design-mission
only for now (the only mission kind with a real multi-step wizard to gate);
`step_key` isn't FK-constrained to any enum since the step vocabulary is
mission-kind-specific and lives in code (`DESIGN_STEP_LABELS`), not in the
DB.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class MissionStepGate(Base):
    __tablename__ = "mission_step_gates"
    __table_args__ = (
        PrimaryKeyConstraint("cohort_id", "mission_id", "step_key", name="pk_mission_step_gates"),
    )

    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False)
    step_key = Column(String(20), nullable=False)
    is_unlocked = Column(Boolean, nullable=False, default=False, server_default="false")
    updated_at = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
