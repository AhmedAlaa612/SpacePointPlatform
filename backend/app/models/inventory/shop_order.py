import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class ShopOrder(Base):
    """Customer purchase or pre-order made through the Ground Station shop."""

    __tablename__ = "shop_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number = Column(String(32), unique=True, nullable=False, index=True)

    # Customer Contact Info
    customer_name = Column(String(255), nullable=False)
    customer_email = Column(String(255), nullable=False, index=True)
    customer_phone = Column(String(50), nullable=True)

    # Shipping details: {"street": "...", "city": "...", "emirate": "...", "country": "...", "postal_code": "..."}
    shipping_address = Column(JSONB, nullable=False, default=dict)

    # Status tracking
    # pending_payment -> paid -> processing -> fulfilled -> cancelled / refunded
    status = Column(String(32), nullable=False, default="pending_payment", index=True)
    # standard | pre_order | mixed
    order_type = Column(String(32), nullable=False, default="standard")

    # Financials (AED)
    total_amount_aed = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="AED")

    # Stripe Reference IDs
    stripe_payment_intent_id = Column(String(255), nullable=True, index=True)
    stripe_checkout_session_id = Column(String(255), nullable=True, index=True)

    # Fulfillment Tracking
    fulfilled_warehouse_id = Column(
        UUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="SET NULL"),
        nullable=True,
    )
    fulfilled_at = Column(DateTime(timezone=True), nullable=True)
    fulfillment_notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    items = relationship(
        "ShopOrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    fulfilled_warehouse = relationship("Warehouse", foreign_keys=[fulfilled_warehouse_id], lazy="selectin")


class ShopOrderItem(Base):
    """Line item in a ShopOrder."""

    __tablename__ = "shop_order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("shop_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shop_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("shop_items.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Snapshots at time of purchase
    item_name = Column(String(255), nullable=False)
    unit_price_aed = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    is_preorder = Column(Boolean, nullable=False, default=False)

    order = relationship("ShopOrder", back_populates="items")
    shop_item = relationship("ShopItem", foreign_keys=[shop_item_id], lazy="selectin")
