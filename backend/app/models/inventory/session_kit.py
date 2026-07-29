import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class SessionKit(Base):
    """A kit ops has earmarked for a session.

    Distinct from custody: assigning a kit on Tuesday and physically handing it
    over on Thursday are different events. This is the plan; `movements` is
    what actually happened. Keeping them separate is what lets the pre-session
    check say "you were supposed to have five kits and you confirmed four".
    """

    __tablename__ = "session_kits"
    __table_args__ = (
        UniqueConstraint("session_id", "kit_id", name="uq_session_kit"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kit_id = Column(
        UUID(as_uuid=True), ForeignKey("kits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class KitCheck(Base):
    """Someone counted a kit — before a workshop, after it, or ad hoc.

    `missing` is a **snapshot**, not derived at read time. A template's bill of
    materials changes; what was missing on the day does not. Recomputing an old
    check against today's BOM would quietly rewrite history.

    `skipped` exists so "chose to proceed without counting" is distinguishable
    from "hasn't got to it yet". The pre-session check is a soft gate (an
    instructor standing in front of thirty students must be able to start), so
    skipping has to be recordable rather than merely possible — otherwise a
    post-check shortage has no baseline and nobody can tell whether the kit
    arrived that way.
    """

    __tablename__ = "kit_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kit_id = Column(
        UUID(as_uuid=True), ForeignKey("kits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SET NULL: a deleted session must not erase the record that somebody
    # counted this kit and found things missing.
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    phase = Column(String(8), nullable=False)  # pre|post|adhoc
    skipped = Column(Boolean, nullable=False, default=False)
    checked_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    # {item_id: counted_qty} — empty when skipped.
    counts = Column(JSONB, nullable=False, default=dict)
    # {item_id: short_by} at save time. Snapshot, see above.
    missing = Column(JSONB, nullable=False, default=dict)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
