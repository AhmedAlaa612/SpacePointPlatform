import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class ShopItem(Base):
    """Ground Station storefront product (Step 7).

    The sellable presentation row. `item_id` optionally links the real
    inventory catalogue row so the storefront can show live stock; NULL
    means merch tracked outside the ledger (pre-order only).
    """

    __tablename__ = "shop_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="SET NULL"), nullable=True)
    slug = Column(String(128), nullable=False, unique=True, index=True)
    display_name = Column(String(255), nullable=False)
    subtitle = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    price_aed = Column(Numeric(10, 2), nullable=False, default=0)
    compare_at_price_aed = Column(Numeric(10, 2), nullable=True)
    cover_image_url = Column(String(512), nullable=True)
    gallery_images = Column(JSONB, nullable=False, default=list, server_default="[]")
    is_published = Column(Boolean, nullable=False, default=False, index=True)
    is_preorder_enabled = Column(Boolean, nullable=False, default=True)
    preorder_message = Column(
        String(255),
        nullable=False,
        default="Pre-order available — Estimated dispatch within 2-3 weeks",
    )
    display_order = Column(Integer, nullable=False, default=0)
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
