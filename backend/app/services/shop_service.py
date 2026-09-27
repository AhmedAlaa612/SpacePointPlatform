import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import UUID

import stripe
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.inventory.item import Item
from app.models.inventory.movement import Movement
from app.models.inventory.shop_item import ShopItem
from app.models.inventory.shop_order import ShopOrder, ShopOrderItem
from app.models.inventory.stock import StockLevel
from app.models.inventory.warehouse import Warehouse
from app.schemas.shop import (
    ShopCheckoutRequest,
    ShopItemAdminResponse,
    ShopItemPublicResponse,
    ShopWarehouseStock,
)

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


async def get_item_stock_breakdown(
    db: AsyncSession, item_id: UUID
) -> Tuple[int, List[ShopWarehouseStock]]:
    """Calculate total available stock and per-warehouse breakdown for an item across active warehouses."""
    stmt = (
        select(
            Warehouse.id.label("warehouse_id"),
            Warehouse.name.label("warehouse_name"),
            Warehouse.code.label("warehouse_code"),
            func.coalesce(StockLevel.qty, 0).label("qty"),
        )
        .outerjoin(
            StockLevel,
            (StockLevel.warehouse_id == Warehouse.id) & (StockLevel.item_id == item_id),
        )
        .where(Warehouse.is_active == True)
        .order_by(Warehouse.name.asc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    breakdown: List[ShopWarehouseStock] = []
    total_qty = 0
    for row in rows:
        qty = max(0, row.qty or 0)
        total_qty += qty
        if qty > 0:  # Only list warehouses that currently hold stock in breakdown view
            breakdown.append(
                ShopWarehouseStock(
                    warehouse_id=row.warehouse_id,
                    warehouse_name=row.warehouse_name,
                    warehouse_code=row.warehouse_code,
                    qty=qty,
                )
            )

    return total_qty, breakdown


async def build_admin_shop_item_response(
    db: AsyncSession, shop_item: ShopItem
) -> ShopItemAdminResponse:
    """Hydrate a ShopItem model into an administrative response with stock and catalog metadata."""
    total_stock, breakdown = await get_item_stock_breakdown(db, shop_item.item_id)
    stock_status = "in_stock" if total_stock > 0 else "pre_order"

    # Catalog fallback metadata
    catalog_name = shop_item.item.name if shop_item.item else "Unknown Item"
    catalog_cat = shop_item.item.category if shop_item.item else "merch"

    return ShopItemAdminResponse(
        id=shop_item.id,
        item_id=shop_item.item_id,
        slug=shop_item.slug,
        display_name=shop_item.display_name,
        subtitle=shop_item.subtitle,
        description=shop_item.description,
        price_aed=shop_item.price_aed,
        compare_at_price_aed=shop_item.compare_at_price_aed,
        cover_image_url=shop_item.cover_image_url,
        gallery_images=shop_item.gallery_images or [],
        is_published=shop_item.is_published,
        is_preorder_enabled=shop_item.is_preorder_enabled,
        preorder_message=shop_item.preorder_message,
        display_order=shop_item.display_order,
        catalog_item_name=catalog_name,
        catalog_item_category=catalog_cat,
        total_stock=total_stock,
        warehouse_breakdown=breakdown,
        stock_status=stock_status,
        created_at=shop_item.created_at,
        updated_at=shop_item.updated_at,
    )


async def build_public_shop_item_response(
    db: AsyncSession, shop_item: ShopItem
) -> ShopItemPublicResponse:
    """Hydrate a ShopItem model for unauthenticated public display."""
    total_stock, _ = await get_item_stock_breakdown(db, shop_item.item_id)
    stock_status = "in_stock" if total_stock > 0 else "pre_order"

    return ShopItemPublicResponse(
        id=shop_item.id,
        slug=shop_item.slug,
        display_name=shop_item.display_name,
        subtitle=shop_item.subtitle,
        description=shop_item.description,
        price_aed=shop_item.price_aed,
        compare_at_price_aed=shop_item.compare_at_price_aed,
        cover_image_url=shop_item.cover_image_url,
        gallery_images=shop_item.gallery_images or [],
        total_stock=total_stock,
        stock_status=stock_status,
        is_preorder_enabled=shop_item.is_preorder_enabled,
        preorder_message=shop_item.preorder_message,
    )


def generate_order_number() -> str:
    """Generate a clean, professional order reference code."""
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    short_suffix = uuid.uuid4().hex[:5].upper()
    return f"SP-ORD-{date_str}-{short_suffix}"


async def create_checkout_session(
    db: AsyncSession,
    request: ShopCheckoutRequest,
    base_url: str = "http://localhost:4321",
) -> Tuple[ShopOrder, Optional[str], Optional[str]]:
    """Create a pending shop order and generate a Stripe Checkout Session."""
    order_number = generate_order_number()
    total_amount = Decimal("0.00")
    order_items: List[ShopOrderItem] = []
    stripe_line_items = []
    has_preorder = False
    has_standard = False

    for item_req in request.items:
        # Fetch shop item with underlying item
        stmt = (
            select(ShopItem)
            .options(selectinload(ShopItem.item))
            .where(ShopItem.id == item_req.shop_item_id, ShopItem.is_published == True)
        )
        res = await db.execute(stmt)
        shop_item = res.scalar_one_or_none()
        if not shop_item:
            raise ValueError(f"Shop item with ID {item_req.shop_item_id} is not available.")

        total_stock, _ = await get_item_stock_breakdown(db, shop_item.item_id)
        is_preorder = total_stock < item_req.quantity
        if is_preorder:
            if not shop_item.is_preorder_enabled:
                raise ValueError(f"'{shop_item.display_name}' is currently out of stock.")
            has_preorder = True
        else:
            has_standard = True

        line_total = shop_item.price_aed * item_req.quantity
        total_amount += line_total

        order_items.append(
            ShopOrderItem(
                shop_item_id=shop_item.id,
                item_name=shop_item.display_name,
                unit_price_aed=shop_item.price_aed,
                quantity=item_req.quantity,
                is_preorder=is_preorder,
            )
        )

        # Stripe requires amounts in smallest currency unit (fils / cents: 1 AED = 100 fils)
        amount_fils = int(shop_item.price_aed * 100)
        item_title = shop_item.display_name
        if is_preorder:
            item_title = f"{item_title} (Pre-order)"

        stripe_line_items.append(
            {
                "price_data": {
                    "currency": "aed",
                    "product_data": {
                        "name": item_title,
                        "description": shop_item.subtitle or "SpacePoint Ground Station Gear",
                        "images": [shop_item.cover_image_url] if shop_item.cover_image_url else [],
                    },
                    "unit_amount": amount_fils,
                },
                "quantity": item_req.quantity,
            }
        )

    # Determine order classification
    order_type = "mixed" if (has_preorder and has_standard) else ("pre_order" if has_preorder else "standard")

    order = ShopOrder(
        order_number=order_number,
        customer_name=request.customer_name,
        customer_email=request.customer_email,
        customer_phone=request.customer_phone,
        shipping_address=request.shipping_address,
        status="pending_payment",
        order_type=order_type,
        total_amount_aed=total_amount,
        currency="AED",
        items=order_items,
    )
    db.add(order)
    await db.flush()

    checkout_url: Optional[str] = None
    session_id: Optional[str] = None

    # If Stripe is configured with a key, create session; otherwise simulate for dev testing
    if settings.STRIPE_SECRET_KEY:
        try:
            success_url = request.success_url or f"{base_url}/shop?order_success={order.order_number}"
            cancel_url = request.cancel_url or f"{base_url}/shop?order_cancelled=1"

            session = await stripe.checkout.Session.create_async(
                payment_method_types=["card"],
                line_items=stripe_line_items,
                mode="payment",
                customer_email=request.customer_email,
                client_reference_id=str(order.id),
                metadata={
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    "order_type": order_type,
                },
                success_url=success_url,
                cancel_url=cancel_url,
            )
            order.stripe_checkout_session_id = session.id
            checkout_url = session.url
            session_id = session.id
        except Exception as e:
            logger.error("Failed to create Stripe session for order %s: %s", order.id, e)
            # Mark order as pending manual payment or error
            order.status = "pending_payment"
    else:
        # Development fallback mode
        checkout_url = f"{base_url}/shop?order_success={order.order_number}&mock_stripe=1"
        order.status = "paid"  # Automatically mark paid in local mock mode
        order.stripe_payment_intent_id = f"mock_pi_{order.id}"

    await db.commit()
    await db.refresh(order)
    return order, checkout_url, session_id


async def mark_order_fulfilled(
    db: AsyncSession,
    order_id: UUID,
    warehouse_id: UUID,
    user_id: UUID,
    notes: Optional[str] = None,
) -> ShopOrder:
    """Fulfill a shop order by deducting inventory stock levels from the selected warehouse."""
    stmt = (
        select(ShopOrder)
        .options(selectinload(ShopOrder.items).selectinload(ShopOrderItem.shop_item))
        .where(ShopOrder.id == order_id)
        .with_for_update()
    )
    res = await db.execute(stmt)
    order = res.scalar_one_or_none()
    if not order:
        raise ValueError(f"Shop order {order_id} not found.")

    if order.status == "fulfilled":
        return order  # Idempotent

    # Verify warehouse exists
    wh_stmt = select(Warehouse).where(Warehouse.id == warehouse_id)
    wh = (await db.execute(wh_stmt)).scalar_one_or_none()
    if not wh:
        raise ValueError(f"Warehouse {warehouse_id} not found.")

    # Deduct stock for each line item
    for line in order.items:
        if line.shop_item and line.shop_item.item_id:
            item_id = line.shop_item.item_id
            stock_stmt = (
                select(StockLevel)
                .where(StockLevel.item_id == item_id, StockLevel.warehouse_id == warehouse_id)
                .with_for_update()
            )
            stock_record = (await db.execute(stock_stmt)).scalar_one_or_none()
            if stock_record:
                # Deduct stock, allow going negative if backordered or log warning
                stock_record.qty = max(0, stock_record.qty - line.quantity)
            else:
                # Create stock record if none existed
                new_stock = StockLevel(
                    item_id=item_id,
                    warehouse_id=warehouse_id,
                    qty=0,
                )
                db.add(new_stock)

            # Record an internal Movement entry for audit ledger
            movement = Movement(
                item_id=item_id,
                qty=line.quantity,
                from_warehouse_id=warehouse_id,
                reason="sold",
                note=f"Shop Order {order.order_number}: Fulfilled via Ground Station shop to {order.customer_name}",
                created_by=user_id,
            )
            db.add(movement)

    order.status = "fulfilled"
    order.fulfilled_warehouse_id = warehouse_id
    order.fulfilled_at = datetime.now(timezone.utc)
    if notes:
        order.fulfillment_notes = notes

    await db.commit()
    await db.refresh(order)
    return order
