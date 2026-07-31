import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Item(Base):
    """The bulk catalogue — one row per *kind* of thing, not per physical
    unit. Covers kit components (EPS board, MPU, M3 screw) and merchandise
    SKUs (Vest L, T-shirt M) in the same table, because both are counted
    rather than serialised and both move through the same ledger.

    Serialised things — a kit, which has its own label and QR — are `Kit`,
    not this.

    The legacy system stored 28 components as 28 hardcoded INTEGER columns on
    `cubesats`, so adding a component was a schema migration; it had already
    been done twice by hand. Here, adding one is a row.
    """

    __tablename__ = "items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(128), nullable=False, unique=True)
    # sensor|board|tool|mechanical|merch|other — grouping for the catalogue
    # UI only; nothing branches on it.
    category = Column(String(32), nullable=False, default="other")

    # Consumables (screws, jumper wires) are excluded from kit checklists
    # entirely and never raise a shortage alert. Twenty M3 screws per kit
    # means a post-workshop count is always "short a few", and an alert that
    # always fires is an alert nobody reads — including the one about the
    # missing ADCS board. They surface as a restock suggestion instead.
    is_consumable = Column(Boolean, nullable=False, default=False)

    # Default for "must this come back?" when the item is issued to a person.
    # Vests and jackets: yes. T-shirts: no. Always overridable per issue —
    # the flag lives on the movement, this is only the default so ops isn't
    # answering the same question fifty times.
    returnable_default = Column(Boolean, nullable=False, default=False)

    notes = Column(Text, nullable=True)

    # Shown to an instructor picking from the equipment shelf (B3) — distinct
    # from `notes`, which is ops-facing. Both optional; most items have
    # neither.
    description = Column(Text, nullable=True)
    image_bucket = Column(String(64), nullable=True)
    image_path = Column(String(512), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
