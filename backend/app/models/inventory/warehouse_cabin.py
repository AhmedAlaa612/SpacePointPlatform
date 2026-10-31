import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class WarehouseCabin(Base):
    """A physical cabin, bin, drawer, or shelf location within a warehouse.

    Staff annotate cabins visually on a warehouse photograph or floorplan using
    (pin_x, pin_y) percentage coordinates (0.0 to 100.0). Items or boxes placed in the
    warehouse can be assigned to cabins.
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
    image_bucket = Column(String(64), nullable=True)
    image_path = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    warehouse = relationship("Warehouse", back_populates="cabins")
    boxes = relationship(
        "WarehouseBox",
        back_populates="cabin",
        cascade="all, delete-orphan",
        order_by="WarehouseBox.sort_order, WarehouseBox.name",
    )
    item_assignments = relationship("ItemCabinAssignment", back_populates="cabin", cascade="all, delete-orphan")


class WarehouseBox(Base):
    """A physical container, box, tub, or tray inside a cabin/shelf.

    Boxes group components together inside a cabin.
    """

    __tablename__ = "warehouse_boxes"
    __table_args__ = (
        UniqueConstraint("cabin_id", "name", name="uq_warehouse_boxes_cabin_name"),
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
    name = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    image_bucket = Column(String(64), nullable=True)
    image_path = Column(String(255), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    warehouse = relationship("Warehouse")
    cabin = relationship("WarehouseCabin", back_populates="boxes")
    item_assignments = relationship("ItemCabinAssignment", back_populates="box", cascade="all, delete-orphan")


class ItemCabinAssignment(Base):
    """Spatial placement of an item within a warehouse/cabin/box.

    An item can sit loose in a cabin (box_id is NULL) or inside a specific box (box_id is set).
    An item can have multiple placements across different boxes or cabins.
    Quantity lives solely on `StockLevel.qty`.
    """

    __tablename__ = "item_cabin_assignments"

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
    box_id = Column(
        UUID(as_uuid=True),
        ForeignKey("warehouse_boxes.id", ondelete="CASCADE"),
        nullable=True,
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
    box = relationship("WarehouseBox", back_populates="item_assignments")
    item = relationship("Item")
    warehouse = relationship("Warehouse")
