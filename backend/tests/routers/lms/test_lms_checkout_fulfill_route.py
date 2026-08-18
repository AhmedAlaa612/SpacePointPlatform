"""`POST /lms/checkout/session/{session_id}/fulfill` — the success-page
trigger. Auth exists not to prevent fraud (the grant always follows the
`purchase_id` in Stripe's own session metadata, never the caller) but so
this route isn't a free proxy for hammering Stripe's API with fabricated
session IDs.
"""

import types
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import status as http_status

import stripe
from app.core.security import create_access_token
from app.models.lms import Course, Enrollment
from app.models.lms.purchase import Purchase
from app.models.user import User


async def _user(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Fulfill Route User", email=f"fr-{uuid.uuid4().hex[:8]}@example.com",
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


@pytest.mark.asyncio
async def test_fulfill_route_completes_a_session_not_yet_processed_by_webhook(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase = await _purchase(db, user=student, course=course, stripe_session_id="cs_test_route1")
    await db.commit()

    session = types.SimpleNamespace(
        metadata={"purchase_id": str(purchase.id)}, payment_status="paid",
        amount_total=course.price_cents, currency=course.currency, payment_intent="pi_route1",
    )
    monkeypatch.setattr(stripe.checkout.Session, "retrieve_async", AsyncMock(return_value=session))

    resp = await client.post(
        f"/lms/checkout/session/cs_test_route1/fulfill", headers=_headers(student),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "paid"
    assert body["course_id"] == str(course.id)

    await db.refresh(purchase)
    assert purchase.status == "paid"
    enrollment = await db.get(Enrollment, purchase.enrollment_id)
    assert enrollment.status == "active"


@pytest.mark.asyncio
async def test_fulfill_route_requires_auth(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase = await _purchase(db, user=student, course=course, stripe_session_id="cs_test_route2")
    await db.commit()

    monkeypatch.setattr(stripe.checkout.Session, "retrieve_async", AsyncMock())

    resp = await client.post(f"/lms/checkout/session/cs_test_route2/fulfill")
    assert resp.status_code == http_status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_fulfill_route_403s_for_a_different_user(db, client, monkeypatch):
    author = await _user(db)
    owner = await _user(db)
    intruder = await _user(db)
    course = await _course(db, author=author)
    purchase = await _purchase(db, user=owner, course=course, stripe_session_id="cs_test_route3")
    await db.commit()

    session = types.SimpleNamespace(
        metadata={"purchase_id": str(purchase.id)}, payment_status="paid",
        amount_total=course.price_cents, currency=course.currency, payment_intent="pi_route3",
    )
    monkeypatch.setattr(stripe.checkout.Session, "retrieve_async", AsyncMock(return_value=session))

    resp = await client.post(
        f"/lms/checkout/session/cs_test_route3/fulfill", headers=_headers(intruder),
    )
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN

    # The 403 exists to stop a stranger from using this route as a free
    # proxy for probing Stripe with fabricated session IDs — not because the
    # grant itself would ever go to the wrong person. Stripe's own session
    # metadata is what fulfill() trusts, never the caller: nothing about the
    # purchase this intruder's call touched belongs to them, whatever partial
    # state it left behind in-session (never committed either way — the real
    # `get_db` gives every request its own session, torn down uncommitted on
    # exception; this test's shared-session fixture is the one place that
    # in-flight state is even observable, which is a fixture artifact, not
    # production behaviour).
    from sqlalchemy import select as sa_select
    no_enrollment_for_intruder = (await db.execute(
        sa_select(Enrollment).where(Enrollment.user_id == intruder.id)
    )).scalars().first()
    assert no_enrollment_for_intruder is None
