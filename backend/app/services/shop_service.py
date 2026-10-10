"""Ground Station shop service (Step 7).

Checkout sessions (Stripe AED when configured, deterministic mock URLs
otherwise), webhook settlement, and paid-order fulfillment with ledger
movements. Orders are always created before any Stripe call so the
webhook has a row to settle — same row-first convention as LMS purchases.
"""

import logging
import secrets
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.inventory.movement import Movement
from app.models.inventory.shop_item import ShopItem
from app.models.inventory.shop_order import ShopOrder, ShopOrderItem
from app.models.inventory.stock import StockLevel
from app.schemas.shop import ShopCheckoutRequest, ShopItemPublicResponse

logger = logging.getLogger(__name__)

SHOP_SITE_URL = "https://spacepoint.ae/shop"

SHOP_ORDER_STATUSES = ("pending_payment", "paid", "fulfilled", "failed", "expired")


def generate_order_number() -> str:
    return f"SP-{datetime.now(timezone.utc).year}-{secrets.token_hex(3).upper()}"


def to_fils(amount_aed: Decimal | float) -> int:
    """Stripe takes integer minor units (fils for AED)."""
    return int(round(Decimal(str(amount_aed)) * 100))


async def compute_stock(db: AsyncSession, item: ShopItem) -> int:
    """Total loose units across all warehouses for the linked catalogue
    row; 0 when the product isn't ledger-tracked."""
    if item.item_id is None:
        return 0
    total = (
        await db.execute(
            select(func.coalesce(func.sum(StockLevel.qty), 0)).where(
                StockLevel.item_id == item.item_id
            )
        )
    ).scalar()
    return int(total or 0)


async def to_public_response(db: AsyncSession, item: ShopItem) -> ShopItemPublicResponse:
    stock = await compute_stock(db, item)
    return ShopItemPublicResponse(
        id=item.id,
        slug=item.slug,
        display_name=item.display_name,
        subtitle=item.subtitle,
        description=item.description,
        price_aed=float(item.price_aed),
        compare_at_price_aed=float(item.compare_at_price_aed) if item.compare_at_price_aed is not None else None,
        cover_image_url=item.cover_image_url,
        gallery_images=list(item.gallery_images or []),
        total_stock=stock,
        stock_status="in_stock" if stock > 0 else "pre_order",
        is_preorder_enabled=item.is_preorder_enabled,
        preorder_message=item.preorder_message,
    )


async def resolve_shop_item(db: AsyncSession, ref: str) -> ShopItem | None:
    """Match a checkout line by id, then slug, then display name. The site's
    legacy cards submit the product title, so all three must resolve."""
    try:
        candidate = uuid.UUID(str(ref))
    except (ValueError, AttributeError):
        candidate = None
    if candidate is not None:
        row = await db.get(ShopItem, candidate)
        if row is not None:
            return row
    row = (
        await db.execute(select(ShopItem).where(ShopItem.slug == ref))
    ).scalars().first()
    if row is not None:
        return row
    return (
        await db.execute(select(ShopItem).where(ShopItem.display_name == ref))
    ).scalars().first()


def _mock_checkout_url(order: ShopOrder, success_url: str, session_id: str) -> str:
    sep = "&" if "?" in success_url else "?"
    return f"{success_url}{sep}{urlencode({'session_id': session_id, 'mock': '1'})}"


async def create_checkout_session(
    db: AsyncSession,
    payload: ShopCheckoutRequest,
) -> tuple[ShopOrder, str]:
    lines: list[tuple[ShopItem, int]] = []
    total = Decimal("0")
    for entry in payload.items:
        item = await resolve_shop_item(db, entry.shop_item_id)
        if item is None or not item.is_published:
            raise HTTPException(status_code=404, detail=f"Product not available: {entry.shop_item_id}")
        lines.append((item, entry.quantity))
        total += Decimal(str(item.price_aed)) * entry.quantity

    order = ShopOrder(
        id=uuid.uuid4(),
        order_number=generate_order_number(),
        customer_name=payload.customer_name.strip(),
        customer_email=payload.customer_email.strip().lower(),
        customer_phone=(payload.customer_phone or "").strip() or None,
        shipping_address=payload.shipping_address.model_dump(),
        status="pending_payment",
        total_amount_aed=total,
        currency="AED",
    )
    db.add(order)
    await db.flush()
    for item, qty in lines:
        db.add(
            ShopOrderItem(
                id=uuid.uuid4(),
                order_id=order.id,
                shop_item_id=item.id,
                item_name=item.display_name,
                unit_price_aed=item.price_aed,
                quantity=qty,
                is_preorder=item.is_preorder_enabled,
            )
        )

    success_url = payload.success_url or f"{SHOP_SITE_URL}?success=1"
    cancel_url = payload.cancel_url or SHOP_SITE_URL

    if settings.STRIPE_SECRET_KEY:
        import stripe

        stripe.api_key = settings.STRIPE_SECRET_KEY
        session = await stripe.checkout.Session.create_async(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "aed",
                        "unit_amount": to_fils(item.price_aed),
                        "product_data": {"name": item.display_name},
                    },
                    "quantity": qty,
                }
                for item, qty in lines
            ],
            success_url=success_url + ("&" if "?" in success_url else "?")
            + "session_id={CHECKOUT_SESSION_ID}",
            cancel_url=cancel_url,
            customer_email=order.customer_email,
            metadata={"shop_order_id": str(order.id), "order_number": order.order_number},
            idempotency_key=str(order.id),
        )
        order.stripe_checkout_session_id = session.id
        checkout_url = session.url
    else:
        # Development mock (no STRIPE_SECRET_KEY): no Stripe call, the
        # checkout URL loops straight back to the success page so the
        # storefront flow is testable without credentials.
        logger.warning("STRIPE_SECRET_KEY is empty — issuing mock shop checkout session")
        order.stripe_checkout_session_id = f"mock_cs_{secrets.token_hex(8)}"
        checkout_url = _mock_checkout_url(order, success_url, order.stripe_checkout_session_id)

    await db.commit()
    await db.refresh(order)
    return order, checkout_url


async def settle_checkout_session(
    db: AsyncSession, session_id: str, payment_intent_id: str | None = None
) -> ShopOrder | None:
    """Mark a pending order paid. Idempotent: replays return the row
    unchanged instead of double-settling."""
    order = (
        await db.execute(
            select(ShopOrder).where(ShopOrder.stripe_checkout_session_id == session_id)
        )
    ).scalars().first()
    if order is None:
        return None
    if order.status != "pending_payment":
        return order
    order.status = "paid"
    if payment_intent_id:
        order.stripe_payment_intent_id = payment_intent_id
    order.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(order)
    return order


async def fulfill_order(
    db: AsyncSession,
    order: ShopOrder,
    *,
    warehouse_id,
    notes: str | None,
    actor_user_id,
) -> ShopOrder:
    """Fulfill a paid order: stamp warehouse/notes/time, decrement linked
    ledger stock (floored at zero), and write one `sold` movement per
    stocked line so the ledger stays the single source of truth."""
    if order.status != "paid":
        raise HTTPException(status_code=400, detail=f"Only paid orders can be fulfilled (status: {order.status})")
    order.status = "fulfilled"
    order.fulfilled_warehouse_id = warehouse_id
    order.fulfillment_notes = (notes or "").strip() or None
    order.fulfilled_at = datetime.now(timezone.utc)
    order.updated_at = order.fulfilled_at

    if warehouse_id is not None:
        lines = (
            await db.execute(select(ShopOrderItem).where(ShopOrderItem.order_id == order.id))
        ).scalars().all()
        for line in lines:
            item = await db.get(ShopItem, line.shop_item_id)
            if item is None or item.item_id is None:
                continue
            level = (
                await db.execute(
                    select(StockLevel).where(
                        StockLevel.item_id == item.item_id,
                        StockLevel.warehouse_id == warehouse_id,
                    )
                )
            ).scalars().first()
            available = level.qty if level is not None else 0
            take = min(available, line.quantity)
            if take <= 0:
                continue
            level.qty = available - take
            db.add(
                Movement(
                    id=uuid.uuid4(),
                    item_id=item.item_id,
                    qty=take,
                    from_warehouse_id=warehouse_id,
                    reason="sold",
                    note=f"Shop order {order.order_number}",
                    created_by=actor_user_id,
                )
            )
    await db.commit()
    await db.refresh(order)
    return order
