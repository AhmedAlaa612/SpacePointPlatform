"""`services/lms/checkout.py::fulfill` — the shared fulfilment function both
the webhook and the checkout success page call. Never touches Stripe's
network (both callers already hold a Session object), so no mocking needed
here — just build the fake Session as a plain namespace.
"""

import types
import uuid

import pytest
from sqlalchemy import select

from app.models.lms import Course, Enrollment
from app.models.lms.purchase import Purchase
from app.models.user import User
from app.services.lms.checkout import fulfill


async def _user(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Checkout Fulfil User", email=f"cf-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _course(db, *, author, **kw) -> Course:
    course = Course(
        id=uuid.uuid4(), title=kw.pop("title", f"Course {uuid.uuid4().hex[:8]}"), created_by=author.id,
        is_published=True, access_mode="paid", price_cents=2500, currency="usd", **kw,
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


def _session(*, purchase_id, payment_status="paid", amount_total=2500, currency="usd", payment_intent="pi_test123"):
    return types.SimpleNamespace(
        metadata={"purchase_id": str(purchase_id)},
        payment_status=payment_status,
        amount_total=amount_total,
        currency=currency,
        payment_intent=payment_intent,
    )


@pytest.mark.asyncio
async def test_fulfill_paid_session_grants_enrollment(db):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase = await _purchase(db, user=student, course=course)
    await db.commit()

    result = await fulfill(db, _session(purchase_id=purchase.id))
    await db.commit()

    assert result.status == "paid"
    assert result.paid_at is not None
    assert result.enrollment_id is not None

    enrollment = await db.get(Enrollment, result.enrollment_id)
    assert enrollment is not None
    assert enrollment.user_id == student.id
    assert enrollment.course_id == course.id
    assert enrollment.source == "purchase"
    assert enrollment.status == "active"


@pytest.mark.asyncio
async def test_fulfill_unpaid_session_stays_pending(db):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase = await _purchase(db, user=student, course=course)
    await db.commit()

    result = await fulfill(db, _session(purchase_id=purchase.id, payment_status="unpaid"))
    await db.commit()

    assert result.status == "pending"
    assert result.enrollment_id is None


@pytest.mark.asyncio
async def test_fulfill_called_twice_is_idempotent(db):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase = await _purchase(db, user=student, course=course)
    await db.commit()

    session = _session(purchase_id=purchase.id)
    await fulfill(db, session)
    await db.commit()
    await fulfill(db, session)
    await db.commit()

    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id, Enrollment.course_id == course.id)
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_fulfill_already_refunded_is_untouched(db):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase = await _purchase(db, user=student, course=course, status="refunded")
    await db.commit()

    result = await fulfill(db, _session(purchase_id=purchase.id))
    await db.commit()

    assert result.status == "refunded"
    assert result.enrollment_id is None


@pytest.mark.asyncio
async def test_fulfill_amount_mismatch_still_fulfils(db):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    purchase = await _purchase(db, user=student, course=course)
    await db.commit()

    result = await fulfill(db, _session(purchase_id=purchase.id, amount_total=999999))
    await db.commit()

    assert result.status == "paid"
    assert result.enrollment_id is not None
