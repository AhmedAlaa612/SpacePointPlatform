"""Stripe Checkout — LMS course purchases (Stage S, August Build Brief
Branch 4). Hosted Checkout (not Elements — lower PCI surface), webhook-
driven fulfilment. Never trust the client-side redirect alone as proof of
payment; `/checkout/session/{id}/fulfill` only ever confirms what the
webhook has already established or will shortly establish, via the same
`fulfill()` function.
"""

import logging
import uuid
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import require_lms_student
from app.db.session import get_db
from app.models.lms.course import Course
from app.models.lms.enrollment import Enrollment
from app.models.lms.purchase import Purchase
from app.models.user import User
from app.schemas.lms import CheckoutFulfillOut, CheckoutSessionOut
from app.services.lms import enrollment_is_active
from app.services.lms.checkout import find_purchase_for_dispute, fulfill, get_pending_purchase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lms", tags=["lms-checkout"])

# Only these seven event types are meant to be registered on the Stripe
# Dashboard endpoint — not "all events". Kept here as the canonical list this
# handler actually understands; anything else falls into the no-op branch.
HANDLED_EVENT_TYPES = {
    "checkout.session.completed",
    "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed",
    "checkout.session.expired",
    "charge.refunded",
    "charge.dispute.created",
    "charge.dispute.closed",
}


@router.post("/courses/{course_id}/checkout", response_model=CheckoutSessionOut)
async def start_course_checkout(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_student),
):
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    if course.access_mode != "paid" or not course.price_cents or course.price_cents <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This course isn't set up for purchase")

    active = (await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == current.id, Enrollment.course_id == course.id, *enrollment_is_active(),
        )
    )).scalars().first()
    if active is not None:
        return CheckoutSessionOut(checkout_url=f"{settings.FRONTEND_URL}/learn/courses/{course.id}")

    # Resume an in-progress purchase rather than starting a second one —
    # covers two tabs, back button, refresh mid-redirect.
    existing = await get_pending_purchase(db, user_id=current.id, course_id=course.id)
    if existing is not None:
        if existing.stripe_session_id:
            session = await stripe.checkout.Session.retrieve_async(existing.stripe_session_id)
            if session.status == "open":
                return CheckoutSessionOut(checkout_url=session.url)
        # Expired, already complete, or the session never got created —
        # retire the dead row so a legitimate retry isn't blocked by it.
        existing.status = "failed"
        await db.flush()

    # Row first, Stripe session second — this ordering is what makes the
    # partial unique index a cheap backstop: the losing insert fails before
    # Stripe is ever contacted, so there is no orphaned session to clean up.
    try:
        purchase = Purchase(
            id=uuid.uuid4(), user_id=current.id, product_type="lms_course", course_id=course.id,
            amount_cents=course.price_cents, currency=course.currency,
        )
        db.add(purchase)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        winner = await get_pending_purchase(db, user_id=current.id, course_id=course.id)
        if winner is not None and winner.stripe_session_id:
            session = await stripe.checkout.Session.retrieve_async(winner.stripe_session_id)
            if session.status == "open":
                return CheckoutSessionOut(checkout_url=session.url)
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Checkout already starting — try again in a moment")

    session = await stripe.checkout.Session.create_async(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": course.currency,
                "unit_amount": course.price_cents,
                "product_data": {"name": course.title},
            },
            "quantity": 1,
        }],
        success_url=f"{settings.FRONTEND_URL}/learn/checkout/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.FRONTEND_URL}/learn/courses/{course.id}",
        customer_email=current.email,
        client_reference_id=str(current.id),
        metadata={"purchase_id": str(purchase.id)},
        idempotency_key=str(purchase.id),
    )
    purchase.stripe_session_id = session.id
    await db.commit()
    return CheckoutSessionOut(checkout_url=session.url)


@router.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except stripe.SignatureVerificationError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    if event.type not in HANDLED_EVENT_TYPES:
        return {"status": "ignored"}

    obj = event.data.object

    if event.type in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        await fulfill(db, obj)

    elif event.type in ("checkout.session.expired", "checkout.session.async_payment_failed"):
        purchase = (await db.execute(
            select(Purchase).where(Purchase.id == uuid.UUID(obj.metadata["purchase_id"]))
        )).scalars().first()
        if purchase is not None and purchase.status == "pending":
            purchase.status = "failed"

    elif event.type == "charge.refunded":
        if obj.refunded:
            purchase = (await db.execute(
                select(Purchase).where(Purchase.stripe_payment_intent_id == obj.payment_intent)
            )).scalars().first()
            # Guard matters here specifically: everywhere else in this
            # handler, redelivering the same event just re-writes the same
            # value. Without this check a redelivered charge.refunded (Stripe
            # explicitly documents redelivery) would overwrite refunded_at
            # with a later, wrong timestamp on every retry.
            if purchase is not None and purchase.status != "refunded":
                purchase.status = "refunded"
                purchase.refunded_at = datetime.now(timezone.utc)
                if purchase.enrollment_id:
                    enrollment = await db.get(Enrollment, purchase.enrollment_id)
                    if enrollment is not None:
                        enrollment.status = "inactive"
        else:
            logger.info("Partial refund on charge %s — no access change", getattr(obj, "id", "?"))

    elif event.type == "charge.dispute.created":
        if obj.status in ("needs_response", "under_review"):
            purchase = await find_purchase_for_dispute(db, obj)
            if purchase is not None and purchase.status != "disputed":
                purchase.status = "disputed"
                if purchase.enrollment_id:
                    enrollment = await db.get(Enrollment, purchase.enrollment_id)
                    if enrollment is not None:
                        enrollment.status = "inactive"
        else:
            # warning_needs_response | warning_under_review | warning_closed |
            # prevented — inquiries/retrievals where funds have not been
            # withdrawn. Revoking here would cost a paying student access
            # over a bank inquiry that may just resolve as warning_closed.
            logger.warning("Dispute inquiry received, status=%s", obj.status)

    elif event.type == "charge.dispute.closed":
        purchase = await find_purchase_for_dispute(db, obj)
        if purchase is not None and purchase.status == "disputed":
            if obj.status in ("won", "warning_closed"):
                purchase.status = "paid"  # money retained, so that's what it is
            # "lost" stays disputed. Never auto-restore the enrollment either
            # way — revoke is automatic, re-grant is manual via the existing
            # ops path.

    await db.commit()
    return {"status": "handled"}


@router.post("/checkout/session/{session_id}/fulfill", response_model=CheckoutFulfillOut)
async def fulfill_checkout_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_student),
):
    """Success-page trigger. With the webhook configured, Stripe waits up to
    10 seconds for it before redirecting, so this is usually a fast,
    idempotent no-op that just confirms success — but it's what makes "never
    trust the client redirect as proof of payment" true: the redirect is
    only a hint to check, the proof is this server-side retrieve."""
    session = await stripe.checkout.Session.retrieve_async(session_id)
    purchase = await fulfill(db, session)
    if purchase.user_id != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN)
    await db.commit()
    return CheckoutFulfillOut(status=purchase.status, course_id=purchase.course_id)
