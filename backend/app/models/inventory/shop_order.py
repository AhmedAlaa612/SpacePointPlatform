import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class ShopOrder(Base):
    """Ground Station store order (Step 7).

    Lifecycle: pending_payment → paid → fulfilled (failed/expired possible
    on the way). Created before the Stripe session so the webhook always
    has a row to settle — same row-first convention as LMS purchases.
    """

    __tablename__ = "shop_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number = Column(String(32), nullable=False, unique=True)
    customer_name = Column(String(255), nullable=False)
    customer_email = Column(String(255), nullable=False)
    customer_phone = Column(String(50), nullable=True)
    shipping_address = Column(JSONB, nullable=False, default=dict, server_default="{}")
    status = Column(String(32), nullable=False, default="pending_payment")
    order_type = Column(String(32), nullable=False, default="standard")
    total_amount_aed = Column(Numeric(10, 2), nullable=False, default=0)
    currency = Column(String(3), nullable=False, default="AED")
    stripe_payment_intent_id = Column(String(255), nullable=True)
    stripe_checkout_session_id = Column(String(255), nullable=True)
    fulfilled_warehouse_id = Column(
        UUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )
    fulfilled_at = Column(DateTime(timezone=True), nullable=True)
    fulfillment_notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    items = relationship(
        "ShopOrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class ShopOrderItem(Base):
    """Priced snapshot of one line on a shop order — prices are copied at
    checkout so later catalogue edits never rewrite history."""

    __tablename__ = "shop_order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(
        UUID(as_uuid=True), ForeignKey("shop_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    shop_item_id = Column(
        UUID(as_uuid=True), ForeignKey("shop_items.id", ondelete="RESTRICT"), nullable=False
    )
    item_name = Column(String(255), nullable=False)
    unit_price_aed = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    is_preorder = Column(Boolean, nullable=False, default=False)

    order = relationship("ShopOrder", back_populates="items")
