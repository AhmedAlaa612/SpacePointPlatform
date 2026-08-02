import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class CohortOpening(Base):
    """Cohort-level default for what a session should offer (2026-08-01) — the
    template a session with no openings of its own inherits, exactly the same
    override-not-merge shape `services/sessions/materials.py` already uses for
    program -> cohort -> session. The moment ops saves real `SessionOpening`
    rows for one session (the "customize" path in the UI), those override this
    template for that session alone; every other session in the cohort keeps
    inheriting it.

    Deliberately no `is_open` and no filled/remaining columns here: those are
    facts about one specific session's actual assignments and interest, and
    have no meaning at the template level. `openings_for_session` computes
    them against *that session's* SessionInstructor rows even when the shape
    (role/slots/amount) comes from here.
    """

    __tablename__ = "cohort_openings"
    __table_args__ = (
        UniqueConstraint("cohort_id", "role_id", name="uq_cohort_opening_role"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("delivery_roles.id", ondelete="RESTRICT"), nullable=False)
    slots = Column(Integer, nullable=False, default=1)
    amount_aed = Column(Numeric(10, 2), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
