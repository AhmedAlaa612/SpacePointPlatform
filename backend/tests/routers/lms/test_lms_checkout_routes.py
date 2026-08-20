"""`POST /lms/courses/{course_id}/checkout` — Stripe Checkout Session
creation, the resume-in-progress double-payment protection, and the
400/200-short-circuit branches. Stripe's own network calls are
monkeypatched — never hit the real API in tests.

Not covered here: a genuine two-connection race hitting the partial unique
index / `except IntegrityError` branch. `conftest.py`'s `db` fixture shares
one DB session (and connection) across every request a test makes, so there
is no way to reproduce two truly concurrent transactions — and forcing a
commit to fail synthetically mid-request corrupts SQLAlchemy's async/
greenlet bridge for the rest of that test (tried, confirmed: raises
`MissingGreenlet` on the next query). The mechanism itself — a partial
unique index on `status='pending'` — is a standard, well-understood Postgres
pattern; what's actually being trusted here is that pattern, not something
novel this test suite would catch a regression in.
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
        id=uuid.uuid4(), full_name="Checkout Route User", email=f"cr-{uuid.uuid4().hex[:8]}@example.com",
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


def _fake_created_session(session_id="cs_test_new", url="https://checkout.stripe.com/pay/cs_test_new"):
    return types.SimpleNamespace(id=session_id, url=url)


def _fake_retrieved_session(*, status="open", url="https://checkout.stripe.com/pay/cs_test_existing"):
    return types.SimpleNamespace(status=status, url=url)


@pytest.mark.asyncio
async def test_checkout_creates_session_for_paid_priced_course(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    await db.commit()

    create_mock = AsyncMock(return_value=_fake_created_session())
    monkeypatch.setattr(stripe.checkout.Session, "create_async", create_mock)

    resp = await client.post(f"/lms/courses/{course.id}/checkout", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    assert resp.json()["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_new"

    create_mock.assert_awaited_once()

    from sqlalchemy import select
    purchase = (await db.execute(
        select(Purchase).where(Purchase.user_id == student.id, Purchase.course_id == course.id)
    )).scalars().first()
    assert purchase is not None
    assert purchase.status == "pending"
    assert purchase.product_type == "lms_course"
    assert purchase.stripe_session_id == "cs_test_new"


@pytest.mark.asyncio
async def test_checkout_400s_on_non_paid_course(db, client):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author, access_mode="open", price_cents=None)
    await db.commit()

    resp = await client.post(f"/lms/courses/{course.id}/checkout", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_checkout_400s_on_paid_course_with_no_price(db, client):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author, access_mode="paid", price_cents=None)
    await db.commit()

    resp = await client.post(f"/lms/courses/{course.id}/checkout", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_checkout_short_circuits_when_already_enrolled(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    db.add(Enrollment(
        id=uuid.uuid4(), user_id=student.id, course_id=course.id, source="ops", status="active",
    ))
    await db.commit()

    create_mock = AsyncMock()
    monkeypatch.setattr(stripe.checkout.Session, "create_async", create_mock)

    resp = await client.post(f"/lms/courses/{course.id}/checkout", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    create_mock.assert_not_awaited()

    from sqlalchemy import select
    purchase = (await db.execute(
        select(Purchase).where(Purchase.user_id == student.id, Purchase.course_id == course.id)
    )).scalars().first()
    assert purchase is None


@pytest.mark.asyncio
async def test_checkout_called_twice_while_open_returns_same_url(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    await db.commit()

    created = _fake_created_session()
    create_mock = AsyncMock(return_value=created)
    retrieve_mock = AsyncMock(return_value=_fake_retrieved_session(status="open", url=created.url))
    monkeypatch.setattr(stripe.checkout.Session, "create_async", create_mock)
    monkeypatch.setattr(stripe.checkout.Session, "retrieve_async", retrieve_mock)

    first = await client.post(f"/lms/courses/{course.id}/checkout", headers=_headers(student))
    second = await client.post(f"/lms/courses/{course.id}/checkout", headers=_headers(student))

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["checkout_url"] == second.json()["checkout_url"]
    create_mock.assert_awaited_once()

    from sqlalchemy import select
    rows = (await db.execute(
        select(Purchase).where(Purchase.user_id == student.id, Purchase.course_id == course.id)
    )).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_checkout_retries_after_expiry_starts_fresh(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    await db.commit()

    create_mock = AsyncMock(side_effect=[
        _fake_created_session(session_id="cs_test_1", url="https://checkout.stripe.com/pay/cs_test_1"),
        _fake_created_session(session_id="cs_test_2", url="https://checkout.stripe.com/pay/cs_test_2"),
    ])
    retrieve_mock = AsyncMock(return_value=_fake_retrieved_session(status="expired"))
    monkeypatch.setattr(stripe.checkout.Session, "create_async", create_mock)
    monkeypatch.setattr(stripe.checkout.Session, "retrieve_async", retrieve_mock)

    first = await client.post(f"/lms/courses/{course.id}/checkout", headers=_headers(student))
    second = await client.post(f"/lms/courses/{course.id}/checkout", headers=_headers(student))

    assert first.json()["checkout_url"] != second.json()["checkout_url"]
    assert create_mock.await_count == 2

    from sqlalchemy import select
    rows = (await db.execute(
        select(Purchase).where(Purchase.user_id == student.id, Purchase.course_id == course.id)
        .order_by(Purchase.created_at)
    )).scalars().all()
    assert len(rows) == 2
    assert rows[0].status == "failed"
    assert rows[1].status == "pending"


@pytest.mark.asyncio
async def test_a_failed_purchase_does_not_block_a_fresh_pending_one(db):
    """The partial index is scoped to status='pending' specifically so a
    retry after a failed/completed attempt is never blocked by it."""
    author = await _user(db)
    student = await _user(db)
    course = await _course(db, author=author)
    await db.commit()

    old = Purchase(
        id=uuid.uuid4(), user_id=student.id, product_type="lms_course", course_id=course.id,
        amount_cents=course.price_cents, currency=course.currency, status="failed",
    )
    db.add(old)
    await db.commit()

    fresh = Purchase(
        id=uuid.uuid4(), user_id=student.id, product_type="lms_course", course_id=course.id,
        amount_cents=course.price_cents, currency=course.currency, status="pending",
    )
    db.add(fresh)
    await db.commit()  # must not raise
