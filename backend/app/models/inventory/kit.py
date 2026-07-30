import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Kit(Base):
    """One physical kit — a box with a label on it. Serialised, unlike `Item`.

    **Location is always set; holder is optional.** A kit out with an
    instructor still has a location (where it belongs / where it came from),
    so "what is in Dubai right now" always answers. An earlier draft made
    these mutually exclusive with a CHECK constraint, which broke exactly that
    query the moment a kit went out — the constraint was removed rather than
    worked around.

    Both columns are denormalised from the movement ledger and written in the
    same transaction as the movement that changes them. Kit lists read them on
    every render; deriving from the ledger each time would be worse. Bulk
    holdings ("who has a vest") are *not* denormalised — they're derived from
    open movements, so there is no second source of truth to drift.
    """

    __tablename__ = "kits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(
        UUID(as_uuid=True), ForeignKey("kit_templates.id", ondelete="RESTRICT"), nullable=False
    )

    # Human key, printed on the box: SP-SATKIT-0001. Searched by, quoted in
    # WhatsApp, written on a sticker — never normalised or reformatted.
    label = Column(String(32), nullable=False, unique=True)

    # QR payload. Deliberately NOT the label: a QR must never encode a
    # guessable identifier (same rule as ticket tokens — see
    # services/documents/ticket.py). Both go on the sticker; only this one
    # goes in the code.
    public_token = Column(String(64), nullable=False, unique=True)

    # working|damaged|retired|lost. `damaged` is reversible and anyone can
    # flag it; `retired`/`lost` are terminal and ops-only.
    status = Column(String(16), nullable=False, default="working")

    current_location_id = Column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    # NULL = sitting at its location. Set = out with this person.
    # SET NULL, never CASCADE: a staff member leaving must not erase the
    # custody record of the kit they were holding (the legacy DB had 14 of 35
    # kits assigned to someone who had left). Same reasoning as
    # attendance_records.recorded_by_user_id.
    current_holder_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # I3-1. "The storekeeper looked, and the shelf was empty." Deliberately
    # NOT a fulfilment-task table: the task *is* the shortage, which is
    # computed, and fulfilling one makes it disappear on its own. The only
    # thing that cannot be derived is this judgment — stock can be replenished
    # tomorrow, so an empty shelf today is not the same fact as someone having
    # checked. §5 collapsed four legacy tables into the movement ledger for
    # exactly this reason; a task table would have been the fifth.
    #
    # A timestamp rather than a boolean, because "waiting three weeks" is the
    # part worth seeing. When procurement lands (I4-*), this column is the
    # purchase trigger rather than a dead end.
    awaiting_parts_since = Column(DateTime(timezone=True), nullable=True)
    awaiting_parts_note = Column(Text, nullable=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class KitItem(Base):
    """How many of an item this specific kit actually contains right now.
    Compared against `KitTemplateItem.required_qty` to compute completeness.
    Rows, not columns — the legacy 28-hardcoded-column design is what this
    replaces."""

    __tablename__ = "kit_items"
    __table_args__ = (
        UniqueConstraint("kit_id", "item_id", name="uq_kit_item"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kit_id = Column(UUID(as_uuid=True), ForeignKey("kits.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    qty = Column(Integer, nullable=False, default=0)
