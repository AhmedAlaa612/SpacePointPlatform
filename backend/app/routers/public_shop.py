"""Public Ground Station shop endpoints — no auth required.

Step 7 — spacepoint.ae/shop reads products here and checks out through
Stripe AED (or the dev mock when no STRIPE_SECRET_KEY is configured).
The webhook verifies signatures in production; with no webhook secret
(dev/test) it accepts a plain {"session_id"} settle call instead.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.inventory.shop_item import ShopItem
from app.schemas.shop import ShopCheckoutRequest, ShopCheckoutResponse, ShopItemPublicResponse
from app.services.shop_service import (
    create_checkout_session,
    settle_checkout_session,
    to_public_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/public/shop", tags=["public-shop"])


@router.get("/products", response_model=list[ShopItemPublicResponse])
async def list_public_products(
    category: str | None = None, db: AsyncSession = Depends(get_db)
):
    try:
        rows = (
            await db.execute(
                select(ShopItem)
                .where(ShopItem.is_published.is_(True))
                .order_by(ShopItem.display_order, ShopItem.display_name)
            )
        ).scalars().all()
    except Exception:
        return []
    # `category` is accepted for forward compatibility; the catalogue has
    # no category column yet, so it currently narrows nothing.
    _ = category
    return [await to_public_response(db, row) for row in rows]


@router.get("/products/{slug}", response_model=ShopItemPublicResponse)
async def get_public_product(slug: str, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            select(ShopItem).where(ShopItem.slug == slug, ShopItem.is_published.is_(True))
        )
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return await to_public_response(db, row)


@router.post("/checkout", response_model=ShopCheckoutResponse)
async def start_shop_checkout(body: ShopCheckoutRequest, db: AsyncSession = Depends(get_db)):
    order, checkout_url = await create_checkout_session(db, body)
    return ShopCheckoutResponse(
        order_id=order.id, order_number=order.order_number, checkout_url=checkout_url
    )


@router.post("/webhook")
async def shop_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    if settings.STRIPE_WEBHOOK_SECRET:
        import stripe

        sig_header = request.headers.get("stripe-signature", "")
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
        except stripe.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
        if event["type"] != "checkout.session.completed":
            return {"received": True}
        session_obj = event["data"]["object"]
        order = await settle_checkout_session(
            db, session_obj["id"], session_obj.get("payment_intent")
        )
        if order is None:
            logger.warning("Shop webhook for unknown session %s", session_obj.get("id"))
            return {"received": True}
        return {"received": True, "order_number": order.order_number, "status": order.status}

    # No webhook secret (dev/test): plain settle call, never in production.
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Expected JSON body with session_id")
    session_id = (data or {}).get("session_id", "")
    if not session_id:
        raise HTTPException(status_code=400, detail="Expected JSON body with session_id")
    order = await settle_checkout_session(db, session_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Unknown checkout session")
    return {"received": True, "order_number": order.order_number, "status": order.status}
