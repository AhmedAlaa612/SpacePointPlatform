import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class KitTemplate(Base):
    """What a kit of a given type is supposed to contain. Two exist today:
    SATKIT and MPKIT (operator-confirmed — a workshop may use either, both, or
    neither).

    `code` is the label prefix, so a SATKIT is labelled `SP-SATKIT-0001`.
    Four digits, and the type rather than the country: a kit moves between
    UAE and Egypt, and re-labelling a physical box is slow, so encoding
    location in the label guarantees the sticker eventually lies.
    """

    __tablename__ = "kit_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(64), nullable=False)          # "SatKit v1"
    code = Column(String(16), nullable=False, unique=True)  # "SATKIT" — label prefix
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class KitTemplateItem(Base):
    """One line of a template's bill of materials: how many of an item a
    complete kit needs. Completeness is computed against these rows, never
    stored on the kit — the legacy system stored an `iscomplete` boolean and a
    `missingitems` text blob that drifted out of date the moment anyone
    touched the counts.

    Every line counts toward completeness — there is no exemption for small
    parts (operator decision, 2026-08-01, reversing the earlier
    `is_consumable` exclusion). A kit is either fully stocked against its
    template or it isn't.
    """

    __tablename__ = "kit_template_items"
    __table_args__ = (
        UniqueConstraint("template_id", "item_id", name="uq_kit_template_item"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(
        UUID(as_uuid=True), ForeignKey("kit_templates.id", ondelete="CASCADE"), nullable=False
    )
    # RESTRICT, not CASCADE: deleting a catalogue item must not silently
    # rewrite what a kit is supposed to contain.
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    required_qty = Column(Integer, nullable=False, default=1)
