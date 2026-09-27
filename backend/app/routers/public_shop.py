import json
import logging
from typing import List, Optional
from uuid import UUID

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.session import get_db
from app.models.inventory.shop_item import ShopItem
from app.models.inventory.shop_order import ShopOrder
from app.schemas.shop import (
    ShopCheckoutRequest,
    ShopCheckoutResponse,
    ShopItemPublicResponse,
)
from app.services.shop_service import (
    build_public_shop_item_response,
    create_checkout_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/shop", tags=["public-shop"])


@router.get("/products", response_model=List[ShopItemPublicResponse])
async def list_public_products(
    category: Optional[str] = Query(None, description="Optional category filter"),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve all published shop products with live stock availability and pre-order state."""
    stmt = (
        select(ShopItem)
        .options(selectinload(ShopItem.item))
        .where(ShopItem.is_published == True)
        .order_by(ShopItem.display_order.asc(), ShopItem.created_at.desc())
    )

    res = await db.execute(stmt)
    items = res.scalars().all()

    if category:
        items = [i for i in items if i.item and i.item.category.lower() == category.lower()]

    output = []
    for item in items:
        resp = await build_public_shop_item_response(db, item)
        output.append(resp)

    return output


@router.get("/products/{slug}", response_model=ShopItemPublicResponse)
async def get_public_product_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve detailed specifications for a single shop product by slug."""
    stmt = (
        select(ShopItem)
        .options(selectinload(ShopItem.item))
        .where(ShopItem.slug == slug.strip().lower(), ShopItem.is_published == True)
    )
    res = await db.execute(stmt)
    item = res.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Product not found or not published.")

    return await build_public_shop_item_response(db, item)


@router.post("/checkout", response_model=ShopCheckoutResponse, status_code=status.HTTP_201_CREATED)
async def initiate_checkout(
    request: Request,
    payload: ShopCheckoutRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a pending shop order and return a Stripe Checkout URL (AED)."""
    origin = request.headers.get("origin") or "http://localhost:4321"

    try:
        order, checkout_url, session_id = await create_checkout_session(
            db=db,
            request=payload,
            base_url=origin,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Checkout initiation failed: %s", e)
        raise HTTPException(status_code=500, detail="Checkout session could not be established.")

    return ShopCheckoutResponse(
        order_id=order.id,
        order_number=order.order_number,
        checkout_url=checkout_url,
        session_id=session_id,
        total_amount_aed=order.total_amount_aed,
        order_type=order.order_type,
    )


@router.post("/webhook")
async def stripe_shop_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe payment events for shop orders."""
    payload_body = await request.body()

    if settings.STRIPE_WEBHOOK_SECRET and stripe_signature:
        try:
            event = stripe.Webhook.construct_event(
                payload_body,
                stripe_signature,
                settings.STRIPE_WEBHOOK_SECRET,
            )
        except Exception as e:
            logger.error("Invalid Stripe signature: %s", e)
            raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    else:
        # Development / untrusted mock fallback
        try:
            event = json.loads(payload_body.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event_type = event.get("type") if isinstance(event, dict) else event.type

    if event_type == "checkout.session.completed":
        session_obj = event.get("data", {}).get("object", {}) if isinstance(event, dict) else event.data.object
        session_id = session_obj.get("id")
        payment_intent_id = session_obj.get("payment_intent")

        if session_id:
            stmt = select(ShopOrder).where(ShopOrder.stripe_checkout_session_id == session_id)
            res = await db.execute(stmt)
            order = res.scalar_one_or_none()
            if order:
                order.status = "paid"
                if payment_intent_id:
                    order.stripe_payment_intent_id = payment_intent_id
                await db.commit()
                logger.info("Shop Order %s marked as paid via Stripe session %s", order.order_number, session_id)

    return {"status": "success"}
