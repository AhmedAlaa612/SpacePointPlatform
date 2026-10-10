from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class ShopItemPublicResponse(BaseModel):
    """Public storefront shape — exactly what spacepoint.ae/shop consumes."""

    id: UUID
    slug: str
    display_name: str
    subtitle: Optional[str] = None
    description: Optional[str] = None
    price_aed: float
    compare_at_price_aed: Optional[float] = None
    cover_image_url: Optional[str] = None
    gallery_images: list[str] = []
    total_stock: int = 0
    stock_status: str = "pre_order"
    is_preorder_enabled: bool = True
    preorder_message: str = ""


class ShopItemAdminOut(BaseModel):
    id: UUID
    item_id: Optional[UUID] = None
    slug: str
    display_name: str
    subtitle: Optional[str] = None
    description: Optional[str] = None
    price_aed: float
    compare_at_price_aed: Optional[float] = None
    cover_image_url: Optional[str] = None
    gallery_images: list[str] = []
    is_published: bool
    is_preorder_enabled: bool
    preorder_message: str
    display_order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ShopItemCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=255)
    subtitle: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    price_aed: float = Field(ge=0)
    compare_at_price_aed: Optional[float] = Field(default=None, ge=0)
    cover_image_url: Optional[str] = Field(default=None, max_length=512)
    gallery_images: list[str] = []
    item_id: Optional[UUID] = None
    is_published: bool = False
    is_preorder_enabled: bool = True
    preorder_message: str = Field(
        default="Pre-order available — Estimated dispatch within 2-3 weeks", max_length=255
    )
    display_order: int = 0


class ShopItemUpdate(BaseModel):
    slug: Optional[str] = Field(default=None, min_length=1, max_length=128)
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    subtitle: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    price_aed: Optional[float] = Field(default=None, ge=0)
    compare_at_price_aed: Optional[float] = Field(default=None, ge=0)
    cover_image_url: Optional[str] = Field(default=None, max_length=512)
    gallery_images: Optional[list[str]] = None
    item_id: Optional[UUID] = None
    is_published: Optional[bool] = None
    is_preorder_enabled: Optional[bool] = None
    preorder_message: Optional[str] = Field(default=None, max_length=255)
    display_order: Optional[int] = None


class ShopCheckoutItem(BaseModel):
    shop_item_id: str
    quantity: int = Field(ge=1, le=99)


class ShopAddress(BaseModel):
    street: str = ""
    city: str = ""
    emirate: str = ""
    country: str = ""
    postal_code: Optional[str] = None


class ShopCheckoutRequest(BaseModel):
    items: list[ShopCheckoutItem] = Field(min_length=1)
    customer_name: str = Field(min_length=1, max_length=255)
    customer_email: EmailStr
    customer_phone: Optional[str] = Field(default=None, max_length=50)
    shipping_address: ShopAddress = ShopAddress()
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class ShopCheckoutResponse(BaseModel):
    order_id: UUID
    order_number: str
    checkout_url: str


class ShopOrderItemOut(BaseModel):
    id: UUID
    shop_item_id: UUID
    item_name: str
    unit_price_aed: float
    quantity: int
    is_preorder: bool


class ShopOrderOut(BaseModel):
    id: UUID
    order_number: str
    customer_name: str
    customer_email: str
    customer_phone: Optional[str] = None
    shipping_address: dict = {}
    status: str
    order_type: str
    total_amount_aed: float
    currency: str
    stripe_checkout_session_id: Optional[str] = None
    fulfilled_warehouse_id: Optional[UUID] = None
    fulfilled_at: Optional[datetime] = None
    fulfillment_notes: Optional[str] = None
    created_at: datetime
    items: list[ShopOrderItemOut] = []

    class Config:
        from_attributes = True


class ShopOrderFulfillIn(BaseModel):
    warehouse_id: Optional[UUID] = None
    notes: Optional[str] = None


ShopOrderStatus = Literal["pending_payment", "paid", "fulfilled", "failed", "expired"]
