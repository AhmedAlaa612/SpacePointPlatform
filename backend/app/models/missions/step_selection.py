"""Per-cohort, per-mission Design step *selection* (2026-08-17) — which of
the 9 build steps even apply to this cohort's run, not whether they're
unlocked yet.

Distinct axis from `MissionStepGate` (`gate.py`): gating is temporal
(instructor paces when a step opens), this is compositional (ops/instructor
decides a step doesn't apply to this cohort at all, e.g. the TDRA Summer
Camp case — Components/Power/Mass only, no Data Budget or Communication).
Both tables can have rows for the same `(cohort_id, mission_id)` at once.

Deliberately does NOT reuse `mission_step_gates`' boolean-flag shape. Writes
here always replace the whole selected set at once (never a single-key
toggle), and a step is included purely by its row existing — there's never
a need to persist "explicitly excluded." A missing row set entirely (no
rows for this `(cohort_id, mission_id)`) means "no selection configured,
all steps included" — the same "absence is the permissive default" rule,
just the opposite polarity from gates' "absence is locked."
"""

from sqlalchemy import Column, DateTime, ForeignKey, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class MissionStepSelection(Base):
    __tablename__ = "mission_step_selections"
    __table_args__ = (
        PrimaryKeyConstraint("cohort_id", "mission_id", "step_key", name="pk_mission_step_selections"),
    )

    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False)
    step_key = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
