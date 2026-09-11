import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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
    """Spatial placement of an item in a specific cabin within a warehouse.

    An item can sit in one primary cabin (the standard 95% case) or be split
    across multiple cabins (e.g. overflow stock in a secondary rack).
    If `qty` is NULL, it indicates placement without a strict quantity partition.
    """

    __tablename__ = "item_cabin_assignments"
    __table_args__ = (
        UniqueConstraint("cabin_id", "item_id", name="uq_item_cabin_assignments_cabin_item"),
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
    qty = Column(Integer, nullable=True)
    notes = Column(String(128), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    cabin = relationship("WarehouseCabin", back_populates="item_assignments")
    item = relationship("Item")
    warehouse = relationship("Warehouse")
