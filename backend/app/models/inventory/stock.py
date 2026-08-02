import uuid

from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class StockLevel(Base):
    """How many of an item sit loose in a warehouse — the running balance.

    Denormalised on purpose, written in the same transaction as the movement
    that changes it. Deriving a balance by summing the whole ledger on every
    page load is the alternative, and it gets slower forever.

    Keyed on warehouse, not location (2026-08-01) — a location can hold
    several warehouses, and two of them each having their own stock of the
    same item is normal, not a conflict. "Stock at a location" is the sum
    across its warehouses, computed via a join, not a stored column.

    No `id`-free composite PK: this codebase uses UUID surrogate keys
    everywhere, and the uniqueness that matters is enforced by the constraint.
    """

    __tablename__ = "stock_levels"
    __table_args__ = (
        UniqueConstraint("item_id", "warehouse_id", name="uq_stock_item_warehouse"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    warehouse_id = Column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False
    )
    qty = Column(Integer, nullable=False, default=0)
