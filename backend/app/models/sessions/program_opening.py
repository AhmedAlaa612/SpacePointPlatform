import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ProgramOpening(Base):
    """A program's default role template (2026-09) — what a new cohort's
    `CohortOpening` rows are seeded from at creation time, nothing more.

    **Copy, not inheritance** (operator decision, 2026-09): unlike
    `DeliveryChecklistItem`'s live program -> cohort -> session chain, this
    is not resolved on read. `create_cohort` copies these rows into real
    `CohortOpening` rows once, at creation; editing the program template
    afterwards never reaches into a cohort that already exists. The roles a
    cohort is staffed with are its own from the moment it's created, not
    something that should shift under an ops person's feet because someone
    edited the program months later. Checklist and materials keep their
    existing live-resolution behavior — this is the one deliberate exception,
    matching how `CohortOpening` itself already isn't live-resolved onto
    `SessionOpening` beyond the one-time "session has no rows of its own"
    fallback `openings_for_session` does at read time (that fallback is
    unaffected by this table — it still stops at the cohort tier).

    Same row shape as `CohortOpening` (slots/rate/responsibilities per role)
    because it exists to become one.
    """

    __tablename__ = "program_openings"
    __table_args__ = (
        UniqueConstraint("program_id", "role_id", name="uq_program_opening_role"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("delivery_roles.id", ondelete="RESTRICT"), nullable=False)
    slots = Column(Integer, nullable=False, default=1)
    amount_aed = Column(Numeric(10, 2), nullable=True)
    notes = Column(Text, nullable=True)
    responsibilities_override = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
