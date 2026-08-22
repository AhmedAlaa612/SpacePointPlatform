"""Stripe Checkout fulfilment (Stage S, August Build Brief Branch 4).

`fulfill()` is the shared function both the webhook and the checkout
success page call — Stripe's own guidance (docs.stripe.com/checkout/
fulfillment) is that both triggers must exist and both must be safe to call
repeatedly, possibly concurrently, for the same session.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.lms.learning_path import LearningPathStep
from app.models.lms.purchase import Purchase
from app.services.lms.enrollment import enroll

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


async def get_pending_purchase(db: AsyncSession, *, user_id: UUID, course_id: UUID) -> Purchase | None:
    return (await db.execute(
        select(Purchase).where(
            Purchase.user_id == user_id, Purchase.course_id == course_id, Purchase.status == "pending",
        )
    )).scalars().first()


async def get_pending_path_purchase(db: AsyncSession, *, user_id: UUID, learning_path_id: UUID) -> Purchase | None:
    return (await db.execute(
        select(Purchase).where(
            Purchase.user_id == user_id, Purchase.learning_path_id == learning_path_id,
            Purchase.status == "pending",
        )
    )).scalars().first()


async def get_purchase_for_update(db: AsyncSession, purchase_id: UUID) -> Purchase:
    """Row-locked read — the entire idempotency story for `fulfill()`. A
    second concurrent caller for the same purchase blocks here, wakes to
    find `status != "pending"`, and returns without enrolling twice."""
    purchase = (await db.execute(
        select(Purchase).where(Purchase.id == purchase_id).with_for_update()
    )).scalars().first()
    if purchase is None:
        raise ValueError(f"Purchase {purchase_id} not found")
    return purchase


async def fulfill(db: AsyncSession, session) -> Purchase:
    """Grant course access for a completed Checkout Session. Never calls
    Stripe — both callers (the webhook, the success-page trigger) already
    hold a `stripe.checkout.Session` object. Does not commit; the caller
    owns the transaction."""
    purchase = await get_purchase_for_update(db, UUID(session.metadata["purchase_id"]))

    if purchase.status != "pending":
        return purchase  # already fulfilled, or refunded/disputed/failed

    if session.payment_status == "unpaid":
        return purchase  # still in progress, or a delayed method settling

    if session.amount_total != purchase.amount_cents or session.currency != purchase.currency:
        logger.error("Stripe purchase amount/currency mismatch: purchase_id=%s", purchase.id)
        # log only — never refuse a payment that actually succeeded

    purchase.status = "paid"
    purchase.paid_at = datetime.now(timezone.utc)
    purchase.stripe_payment_intent_id = session.payment_intent

    if purchase.product_type == "learning_path":
        steps = (await db.execute(
            select(LearningPathStep.course_id).where(LearningPathStep.learning_path_id == purchase.learning_path_id)
        )).scalars().all()
        for course_id in steps:
            await enroll(
                db, user_id=purchase.user_id, course_id=course_id, source="purchase", purchase_id=purchase.id,
            )
        # No single enrollment to point at for a bundle — enrollment_id stays
        # null; Enrollment.purchase_id is the real join for this purchase.
    else:
        enrollment = await enroll(
            db, user_id=purchase.user_id, course_id=purchase.course_id, source="purchase", purchase_id=purchase.id,
        )
        purchase.enrollment_id = enrollment.id
    return purchase


async def find_purchase_for_dispute(db: AsyncSession, dispute) -> Purchase | None:
    """Match a Stripe Dispute object to its purchase. `dispute.payment_intent`
    is documented nullable (docs.stripe.com/api/disputes/object shows it null
    even on a real, populated Dispute); `dispute.charge` is documented as
    always present, so that's the fallback — one extra API call, only paid
    when the free match actually misses, and only inside this low-volume
    branch (never inside `fulfill()`'s locked hot path)."""
    payment_intent_id = dispute.payment_intent
    if payment_intent_id:
        purchase = (await db.execute(
            select(Purchase).where(Purchase.stripe_payment_intent_id == payment_intent_id)
        )).scalars().first()
        if purchase is not None:
            return purchase

    charge = await stripe.Charge.retrieve_async(dispute.charge)
    return (await db.execute(
        select(Purchase).where(Purchase.stripe_payment_intent_id == charge.payment_intent)
    )).scalars().first()
