"""`POST /lms/webhooks/stripe` — signature verification, and every event
branch: fulfilment, expiry, refunds (full + partial + redelivery), disputes
(the `warning_*` inquiry states vs. real chargebacks, the nullable
`payment_intent` fallback), and dispute resolution. No auth on this route —
verified by Stripe's signature instead; `stripe.Webhook.construct_event` is
monkeypatched so no real HMAC or network call happens in tests.
"""

import types
import uuid

import pytest
from fastapi import status as http_status

import stripe
from app.core.security import create_access_token
from app.models.lms import Course, Enrollment
from app.models.lms.purchase import Purchase
from app.models.user import User


async def _user(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Webhook User", email=f"wh-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _course(db, *, author, **kw) -> Course:
    course = Course(
        id=uuid.uuid4(), title=kw.pop("title", f"Course {uuid.uuid4().hex[:8]}"), created_by=author.id,
        is_published=True,
        access_mode=kw.pop("access_mode", "paid"),
        price_cents=kw.pop("price_cents", 2500),
        currency=kw.pop("currency", "usd"),
        **kw,
    )
    db.add(course)
    await db.flush()
    return course


async def _purchase(db, *, user, course, **kw) -> Purchase:
    purchase = Purchase(
        id=uuid.uuid4(), user_id=user.id, product_type="lms_course", course_id=course.id,
        amount_cents=course.price_cents, currency=course.currency,
        status=kw.pop("status", "pending"), **kw,
    )
    db.add(purchase)
    await db.flush()
    return purchase


async def _paid_purchase_with_enrollment(db, *, user, course, **kw) -> tuple[Purchase, Enrollment]:
    """A settled purchase plus the active enrollment it granted — the shape
    `fulfill()` actually produces (`Enrollment.purchase_id` set, mirrored on
    `Purchase.enrollment_id` for the single-course case), so refund/dispute
    revocation (keyed off `Enrollment.purchase_id`) has something to find."""
    purchase = await _purchase(db, user=user, course=course, status="paid", **kw)
    enrollment = Enrollment(
        id=uuid.uuid4(), user_id=user.id, course_id=course.id, source="purchase", status="active",
        purchase_id=purchase.id,
    )
    db.add(enrollment)
    await db.flush()
    purchase.enrollment_id = enrollment.id
    return purchase, enrollment


def _event(event_type: str, obj):
    return types.SimpleNamespace(type=event_type, data=types.SimpleNamespace(object=obj))


def _mock_construct_event(monkeypatch, event):
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **kw: event)


async def _post_webhook(client):
    return await client.post(
        "/lms/webhooks/stripe", content=b"{}", headers={"stripe-signature": "test-sig"},
    )


@pytest.mark.asyncio
async def test_checkout_session_completed_grants_active_enrollment(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase = await _purchase(db, user=student, course=course)
    await db.commit()

    session = types.SimpleNamespace(
        metadata={"purchase_id": str(purchase.id)}, payment_status="paid",
        amount_total=course.price_cents, currency=course.currency, payment_intent="pi_wh_1",
    )
    _mock_construct_event(monkeypatch, _event("checkout.session.completed", session))

    resp = await _post_webhook(client)
    assert resp.status_code == 200, resp.text

    await db.refresh(purchase)
    assert purchase.status == "paid"
    enrollment = await db.get(Enrollment, purchase.enrollment_id)
    assert enrollment.status == "active"


@pytest.mark.asyncio
async def test_redelivered_completed_event_creates_only_one_enrollment(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase = await _purchase(db, user=student, course=course)
    await db.commit()

    session = types.SimpleNamespace(
        metadata={"purchase_id": str(purchase.id)}, payment_status="paid",
        amount_total=course.price_cents, currency=course.currency, payment_intent="pi_wh_2",
    )
    _mock_construct_event(monkeypatch, _event("checkout.session.completed", session))

    await _post_webhook(client)
    await _post_webhook(client)

    from sqlalchemy import select
    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id, Enrollment.course_id == course.id)
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_session_expired_marks_pending_purchase_failed(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase = await _purchase(db, user=student, course=course)
    await db.commit()

    obj = types.SimpleNamespace(metadata={"purchase_id": str(purchase.id)})
    _mock_construct_event(monkeypatch, _event("checkout.session.expired", obj))

    resp = await _post_webhook(client)
    assert resp.status_code == 200, resp.text

    await db.refresh(purchase)
    assert purchase.status == "failed"


@pytest.mark.asyncio
async def test_full_refund_revokes_enrollment(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase, enrollment = await _paid_purchase_with_enrollment(
        db, user=student, course=course, stripe_payment_intent_id="pi_refund_1",
    )
    await db.commit()

    charge = types.SimpleNamespace(id="ch_1", refunded=True, payment_intent="pi_refund_1", amount_refunded=course.price_cents)
    _mock_construct_event(monkeypatch, _event("charge.refunded", charge))

    resp = await _post_webhook(client)
    assert resp.status_code == 200, resp.text

    await db.refresh(purchase)
    await db.refresh(enrollment)
    assert purchase.status == "refunded"
    assert purchase.refunded_at is not None
    assert enrollment.status == "inactive"


@pytest.mark.asyncio
async def test_redelivered_refund_event_does_not_move_the_timestamp(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase, enrollment = await _paid_purchase_with_enrollment(
        db, user=student, course=course, stripe_payment_intent_id="pi_refund_2",
    )
    await db.commit()

    charge = types.SimpleNamespace(id="ch_2", refunded=True, payment_intent="pi_refund_2", amount_refunded=course.price_cents)
    _mock_construct_event(monkeypatch, _event("charge.refunded", charge))

    await _post_webhook(client)
    await db.refresh(purchase)
    first_refunded_at = purchase.refunded_at

    await _post_webhook(client)
    await db.refresh(purchase)

    assert purchase.refunded_at == first_refunded_at


@pytest.mark.asyncio
async def test_partial_refund_changes_nothing(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase, enrollment = await _paid_purchase_with_enrollment(
        db, user=student, course=course, stripe_payment_intent_id="pi_refund_3",
    )
    await db.commit()

    charge = types.SimpleNamespace(id="ch_3", refunded=False, payment_intent="pi_refund_3", amount_refunded=500)
    _mock_construct_event(monkeypatch, _event("charge.refunded", charge))

    resp = await _post_webhook(client)
    assert resp.status_code == 200, resp.text

    await db.refresh(purchase)
    await db.refresh(enrollment)
    assert purchase.status == "paid"
    assert enrollment.status == "active"


@pytest.mark.asyncio
async def test_dispute_created_needs_response_revokes_access(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase, enrollment = await _paid_purchase_with_enrollment(
        db, user=student, course=course, stripe_payment_intent_id="pi_dispute_1",
    )
    await db.commit()

    dispute = types.SimpleNamespace(status="needs_response", payment_intent="pi_dispute_1", charge="ch_dispute_1")
    _mock_construct_event(monkeypatch, _event("charge.dispute.created", dispute))

    resp = await _post_webhook(client)
    assert resp.status_code == 200, resp.text

    await db.refresh(purchase)
    await db.refresh(enrollment)
    assert purchase.status == "disputed"
    assert enrollment.status == "inactive"


@pytest.mark.asyncio
async def test_dispute_created_warning_inquiry_leaves_access_untouched(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase, enrollment = await _paid_purchase_with_enrollment(
        db, user=student, course=course, stripe_payment_intent_id="pi_dispute_2",
    )
    await db.commit()

    dispute = types.SimpleNamespace(status="warning_needs_response", payment_intent="pi_dispute_2", charge="ch_dispute_2")
    _mock_construct_event(monkeypatch, _event("charge.dispute.created", dispute))

    resp = await _post_webhook(client)
    assert resp.status_code == 200, resp.text

    await db.refresh(purchase)
    await db.refresh(enrollment)
    assert purchase.status == "paid"
    assert enrollment.status == "active"


@pytest.mark.asyncio
async def test_dispute_created_with_null_payment_intent_falls_back_to_charge_lookup(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase, enrollment = await _paid_purchase_with_enrollment(
        db, user=student, course=course, stripe_payment_intent_id="pi_dispute_3",
    )
    await db.commit()

    from unittest.mock import AsyncMock
    retrieve_mock = AsyncMock(return_value=types.SimpleNamespace(payment_intent="pi_dispute_3"))
    monkeypatch.setattr(stripe.Charge, "retrieve_async", retrieve_mock)

    dispute = types.SimpleNamespace(status="needs_response", payment_intent=None, charge="ch_dispute_3")
    _mock_construct_event(monkeypatch, _event("charge.dispute.created", dispute))

    resp = await _post_webhook(client)
    assert resp.status_code == 200, resp.text

    retrieve_mock.assert_awaited_once_with("ch_dispute_3")
    await db.refresh(purchase)
    await db.refresh(enrollment)
    assert purchase.status == "disputed"
    assert enrollment.status == "inactive"


@pytest.mark.asyncio
async def test_dispute_closed_won_restores_paid_status_but_not_enrollment(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase, enrollment = await _paid_purchase_with_enrollment(
        db, user=student, course=course, stripe_payment_intent_id="pi_dispute_4",
    )
    purchase.status = "disputed"
    enrollment.status = "inactive"
    await db.commit()

    dispute = types.SimpleNamespace(status="won", payment_intent="pi_dispute_4", charge="ch_dispute_4")
    _mock_construct_event(monkeypatch, _event("charge.dispute.closed", dispute))

    resp = await _post_webhook(client)
    assert resp.status_code == 200, resp.text

    await db.refresh(purchase)
    await db.refresh(enrollment)
    assert purchase.status == "paid"
    assert enrollment.status == "inactive"  # never auto-restored


@pytest.mark.asyncio
async def test_dispute_closed_lost_stays_disputed(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase = await _purchase(db, user=student, course=course, status="disputed",
                                stripe_payment_intent_id="pi_dispute_5")
    await db.commit()

    dispute = types.SimpleNamespace(status="lost", payment_intent="pi_dispute_5", charge="ch_dispute_5")
    _mock_construct_event(monkeypatch, _event("charge.dispute.closed", dispute))

    resp = await _post_webhook(client)
    assert resp.status_code == 200, resp.text

    await db.refresh(purchase)
    assert purchase.status == "disputed"


@pytest.mark.asyncio
async def test_bad_signature_is_rejected(db, client, monkeypatch):
    def raise_sig_error(*a, **kw):
        raise stripe.SignatureVerificationError("bad signature", "sig_header")

    monkeypatch.setattr(stripe.Webhook, "construct_event", raise_sig_error)

    resp = await _post_webhook(client)
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_unhandled_event_type_is_a_no_op(db, client, monkeypatch):
    _mock_construct_event(monkeypatch, _event("customer.created", types.SimpleNamespace()))

    resp = await _post_webhook(client)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
