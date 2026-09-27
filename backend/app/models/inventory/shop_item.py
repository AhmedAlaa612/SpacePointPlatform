import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class ShopItem(Base):
    """A published retail/commercial product in the Ground Station shop.
    
    Points 1:1 to an underlying catalogue `Item` from which it derives physical
    specifications. Inventory stock levels are dynamically calculated across
    all active warehouses and resellers holding stock for `item_id`.
    """

    __tablename__ = "shop_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Public web presence
    slug = Column(String(128), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=False)
    subtitle = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

    # Pricing in AED
    price_aed = Column(Numeric(10, 2), nullable=False)
    compare_at_price_aed = Column(Numeric(10, 2), nullable=True)  # For strikethrough/sale prices

    # Visual assets
    cover_image_url = Column(String(512), nullable=True)
    gallery_images = Column(JSONB, nullable=False, default=list)  # List of image URLs

    # Publishing & Pre-order settings
    is_published = Column(Boolean, nullable=False, default=False, index=True)
    is_preorder_enabled = Column(Boolean, nullable=False, default=True)
    preorder_message = Column(
        String(255),
        nullable=False,
        default="Pre-order available — Estimated dispatch within 2-3 weeks",
    )

    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relations
    item = relationship("Item", foreign_keys=[item_id], lazy="selectin")
