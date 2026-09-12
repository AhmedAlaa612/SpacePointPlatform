import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class WarehouseCabin(Base):
    """A physical cabin, bin, drawer, or shelf location within a warehouse.

    Staff annotate cabins visually on a warehouse photograph or floorplan using
    (pin_x, pin_y) percentage coordinates (0.0 to 100.0). Items placed in the
    warehouse can be assigned to one or more cabins.
    """

    __tablename__ = "warehouse_cabins"
    __table_args__ = (
        UniqueConstraint("warehouse_id", "name", name="uq_warehouse_cabins_warehouse_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    warehouse_id = Column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    pin_x = Column(Float, nullable=True)
    pin_y = Column(Float, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    warehouse = relationship("Warehouse", back_populates="cabins")
    item_assignments = relationship("ItemCabinAssignment", back_populates="cabin", cascade="all, delete-orphan")


class ItemCabinAssignment(Base):
    """Spatial placement of an item within a warehouse — one home per item.

    1:1 per (warehouse, item): an item lives in at most one cabin in a given
    warehouse, or nowhere (unassigned). This row carries location only —
    quantity lives solely on `StockLevel.qty`, so counting stock never has
    to sync two numbers.
    """

    __tablename__ = "item_cabin_assignments"
    __table_args__ = (
        UniqueConstraint("warehouse_id", "item_id", name="uq_item_cabin_assignments_warehouse_item"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    warehouse_id = Column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cabin_id = Column(
        UUID(as_uuid=True),
        ForeignKey("warehouse_cabins.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notes = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    cabin = relationship("WarehouseCabin", back_populates="item_assignments")
    item = relationship("Item")
    warehouse = relationship("Warehouse")
