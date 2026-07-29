import uuid

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class StockLevel(Base):
    """How many of an item sit loose at a location — the running balance.

    Denormalised on purpose, written in the same transaction as the movement
    that changes it. Deriving a balance by summing the whole ledger on every
    page load is the alternative, and it gets slower forever.

    No `id`-free composite PK: this codebase uses UUID surrogate keys
    everywhere, and the uniqueness that matters is enforced by the constraint.
    """

    __tablename__ = "stock_levels"
    __table_args__ = (
        UniqueConstraint("item_id", "location_id", name="uq_stock_item_location"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    location_id = Column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="CASCADE"), nullable=False
    )
    qty = Column(Integer, nullable=False, default=0)
