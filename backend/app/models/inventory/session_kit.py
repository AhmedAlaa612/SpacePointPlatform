import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class SessionKit(Base):
    """A kit ops has earmarked for a session — and the whole session-side
    story of that kit. There is no custody leg: nobody "hands" a kit to an
    instructor and nobody has to hand it back to one. The instructor confirms,
    per kit, that they have it (`received_at`) and later reports it back or
    says it's coming later (`return_status`). Ops reviews that report
    (`ops_confirmed_at`) and, separately and optionally, moves the kit onto a
    shelf — an ordinary inventory move, not something this record triggers.
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

    # The instructor confirming they physically have the kit, pre-session.
    received_at = Column(DateTime(timezone=True), nullable=True)
    received_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # returned | return_later — what the instructor reported, post-session.
    return_status = Column(String(16), nullable=True)
    returned_at = Column(DateTime(timezone=True), nullable=True)
    returned_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    return_note = Column(Text, nullable=True)

    # Ops reviewing that report, in the session review screen.
    ops_confirmed_at = Column(DateTime(timezone=True), nullable=True)
    ops_confirmed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


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
