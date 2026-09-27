from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ShopWarehouseStock(BaseModel):
    warehouse_id: UUID
    warehouse_name: str
    warehouse_code: Optional[str] = None
    qty: int = 0


class ShopItemBase(BaseModel):
    item_id: UUID
    slug: str = Field(..., max_length=128)
    display_name: str = Field(..., max_length=255)
    subtitle: Optional[str] = None
    description: Optional[str] = None
    price_aed: Decimal = Field(..., ge=0)
    compare_at_price_aed: Optional[Decimal] = Field(None, ge=0)
    cover_image_url: Optional[str] = None
    gallery_images: List[str] = Field(default_factory=list)
    is_published: bool = False
    is_preorder_enabled: bool = True
    preorder_message: str = "Pre-order available — Estimated dispatch within 2-3 weeks"
    display_order: int = 0


class ShopItemCreate(ShopItemBase):
    pass


class ShopItemUpdate(BaseModel):
    display_name: Optional[str] = None
    slug: Optional[str] = None
    subtitle: Optional[str] = None
    description: Optional[str] = None
    price_aed: Optional[Decimal] = Field(None, ge=0)
    compare_at_price_aed: Optional[Decimal] = None
    cover_image_url: Optional[str] = None
    gallery_images: Optional[List[str]] = None
    is_published: Optional[bool] = None
    is_preorder_enabled: Optional[bool] = None
    preorder_message: Optional[str] = None
    display_order: Optional[int] = None


class ShopItemAdminResponse(ShopItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    catalog_item_name: str
    catalog_item_category: str
    total_stock: int = 0
    warehouse_breakdown: List[ShopWarehouseStock] = Field(default_factory=list)
    stock_status: str = "in_stock"  # in_stock | pre_order
    created_at: datetime
    updated_at: datetime


class ShopItemPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    display_name: str
    subtitle: Optional[str] = None
    description: Optional[str] = None
    price_aed: Decimal
    compare_at_price_aed: Optional[Decimal] = None
    cover_image_url: Optional[str] = None
    gallery_images: List[str] = Field(default_factory=list)
    total_stock: int = 0
    stock_status: str = "in_stock"  # in_stock | pre_order
    is_preorder_enabled: bool = True
    preorder_message: str = "Pre-order available — Estimated dispatch within 2-3 weeks"


class ShopCheckoutItem(BaseModel):
    shop_item_id: UUID
    quantity: int = Field(default=1, ge=1)


class ShopCheckoutRequest(BaseModel):
    items: List[ShopCheckoutItem]
    customer_name: str = Field(..., min_length=2)
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    shipping_address: Dict[str, Any] = Field(
        ...,
        description="Address object containing street, city, emirate, country, postal_code",
    )
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class ShopCheckoutResponse(BaseModel):
    order_id: UUID
    order_number: str
    checkout_url: Optional[str] = None
    session_id: Optional[str] = None
    client_secret: Optional[str] = None
    total_amount_aed: Decimal
    order_type: str  # standard | pre_order | mixed


class ShopOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    shop_item_id: UUID
    item_name: str
    unit_price_aed: Decimal
    quantity: int
    is_preorder: bool


class ShopOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_number: str
    customer_name: str
    customer_email: str
    customer_phone: Optional[str] = None
    shipping_address: Dict[str, Any]
    status: str
    order_type: str
    total_amount_aed: Decimal
    currency: str = "AED"
    stripe_payment_intent_id: Optional[str] = None
    stripe_checkout_session_id: Optional[str] = None
    fulfilled_warehouse_id: Optional[UUID] = None
    fulfilled_warehouse_name: Optional[str] = None
    fulfilled_at: Optional[datetime] = None
    fulfillment_notes: Optional[str] = None
    created_at: datetime
    items: List[ShopOrderItemResponse] = Field(default_factory=list)


class ShopOrderFulfillRequest(BaseModel):
    warehouse_id: UUID
    notes: Optional[str] = None
