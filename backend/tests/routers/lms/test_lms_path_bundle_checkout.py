"""Learning path bundle pricing (2026-08-21) — `POST /lms/learning-paths/
{id}/checkout`, `fulfill()`'s bundle branch, and refund revocation scoped to
`Enrollment.purchase_id` rather than the single-row `Purchase.enrollment_id`
(which only ever applies to a single-course purchase). Stripe's own network
calls are monkeypatched, same posture as `test_lms_checkout_routes.py`.
"""

import types
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import status as http_status
from sqlalchemy import select

import stripe
from app.core.security import create_access_token
from app.models.lms import Course, Enrollment
from app.models.lms.learning_path import LearningPath, LearningPathStep
from app.models.lms.purchase import Purchase
from app.models.user import User
from app.services.lms.checkout import fulfill


async def _user(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Bundle Checkout User", email=f"bc-{uuid.uuid4().hex[:8]}@example.com",
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
        is_published=True, access_mode=kw.pop("access_mode", "paid"), **kw,
    )
    db.add(course)
    await db.flush()
    return course


async def _path(db, *, author, price_cents=5000, currency="usd", published=True) -> LearningPath:
    path = LearningPath(
        id=uuid.uuid4(), title=f"Bundle {uuid.uuid4().hex[:8]}", created_by=author.id, is_published=published,
        price_cents=price_cents, currency=currency,
    )
    db.add(path)
    await db.flush()
    return path


async def _step(db, *, path, course, position) -> LearningPathStep:
    step = LearningPathStep(id=uuid.uuid4(), learning_path_id=path.id, course_id=course.id, position=position)
    db.add(step)
    await db.flush()
    return step


def _fake_created_session(session_id="cs_bundle_new", url="https://checkout.stripe.com/pay/cs_bundle_new"):
    return types.SimpleNamespace(id=session_id, url=url)


def _session_obj(*, purchase_id, payment_status="paid", amount_total=5000, currency="usd", payment_intent="pi_bundle_1"):
    return types.SimpleNamespace(
        metadata={"purchase_id": str(purchase_id)}, payment_status=payment_status,
        amount_total=amount_total, currency=currency, payment_intent=payment_intent,
    )


# ── checkout endpoint ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_path_checkout_creates_session_for_unowned_bundle(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    path = await _path(db, author=author)
    c1, c2 = await _course(db, author=author), await _course(db, author=author)
    await _step(db, path=path, course=c1, position=1)
    await _step(db, path=path, course=c2, position=2)
    await db.commit()

    create_mock = AsyncMock(return_value=_fake_created_session())
    monkeypatch.setattr(stripe.checkout.Session, "create_async", create_mock)

    resp = await client.post(f"/lms/learning-paths/{path.id}/checkout", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    assert resp.json()["checkout_url"] == "https://checkout.stripe.com/pay/cs_bundle_new"
    create_mock.assert_awaited_once()

    purchase = (await db.execute(
        select(Purchase).where(Purchase.user_id == student.id, Purchase.learning_path_id == path.id)
    )).scalars().first()
    assert purchase is not None
    assert purchase.product_type == "learning_path"
    assert purchase.amount_cents == path.price_cents


@pytest.mark.asyncio
async def test_path_checkout_400s_when_not_purchasable(db, client):
    author = await _user(db)
    student = await _user(db)
    path = await _path(db, author=author, price_cents=None)
    await db.commit()

    resp = await client.post(f"/lms/learning-paths/{path.id}/checkout", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_path_checkout_400s_when_no_steps(db, client):
    author = await _user(db)
    student = await _user(db)
    path = await _path(db, author=author)
    await db.commit()

    resp = await client.post(f"/lms/learning-paths/{path.id}/checkout", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_path_checkout_blocked_when_fully_owned(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    path = await _path(db, author=author)
    c1, c2 = await _course(db, author=author), await _course(db, author=author)
    await _step(db, path=path, course=c1, position=1)
    await _step(db, path=path, course=c2, position=2)
    db.add(Enrollment(id=uuid.uuid4(), user_id=student.id, course_id=c1.id, source="ops", status="active"))
    db.add(Enrollment(id=uuid.uuid4(), user_id=student.id, course_id=c2.id, source="ops", status="active"))
    await db.commit()

    create_mock = AsyncMock()
    monkeypatch.setattr(stripe.checkout.Session, "create_async", create_mock)

    resp = await client.post(f"/lms/learning-paths/{path.id}/checkout", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    create_mock.assert_not_awaited()

    purchase = (await db.execute(
        select(Purchase).where(Purchase.user_id == student.id, Purchase.learning_path_id == path.id)
    )).scalars().first()
    assert purchase is None


@pytest.mark.asyncio
async def test_path_checkout_allowed_when_partially_owned(db, client, monkeypatch):
    """Owning some but not all of the bundle's courses still buys the full
    bundle at full price — no partial/proration logic (operator decision)."""
    author = await _user(db)
    student = await _user(db)
    path = await _path(db, author=author)
    c1, c2 = await _course(db, author=author), await _course(db, author=author)
    await _step(db, path=path, course=c1, position=1)
    await _step(db, path=path, course=c2, position=2)
    db.add(Enrollment(id=uuid.uuid4(), user_id=student.id, course_id=c1.id, source="ops", status="active"))
    await db.commit()

    create_mock = AsyncMock(return_value=_fake_created_session())
    monkeypatch.setattr(stripe.checkout.Session, "create_async", create_mock)

    resp = await client.post(f"/lms/learning-paths/{path.id}/checkout", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    create_mock.assert_awaited_once()

    purchase = (await db.execute(
        select(Purchase).where(Purchase.user_id == student.id, Purchase.learning_path_id == path.id)
    )).scalars().first()
    assert purchase is not None
    assert purchase.amount_cents == path.price_cents  # full price, not prorated


# ── fulfill() bundle branch ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fulfill_bundle_enrolls_every_step_course(db):
    author = await _user(db)
    student = await _user(db)
    path = await _path(db, author=author)
    c1, c2, c3 = [await _course(db, author=author) for _ in range(3)]
    for i, c in enumerate((c1, c2, c3), start=1):
        await _step(db, path=path, course=c, position=i)
    purchase = Purchase(
        id=uuid.uuid4(), user_id=student.id, product_type="learning_path", learning_path_id=path.id,
        amount_cents=path.price_cents, currency=path.currency, status="pending",
    )
    db.add(purchase)
    await db.commit()

    result = await fulfill(db, _session_obj(purchase_id=purchase.id))
    await db.commit()

    assert result.status == "paid"
    assert result.enrollment_id is None  # no single row to point at for a bundle

    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id, Enrollment.purchase_id == purchase.id)
    )).scalars().all()
    assert {r.course_id for r in rows} == {c1.id, c2.id, c3.id}
    assert all(r.status == "active" and r.source == "purchase" for r in rows)


@pytest.mark.asyncio
async def test_fulfill_bundle_leaves_independently_owned_enrollment_unstamped(db):
    """An enrollment the student already had (e.g. open self-enrol) before
    buying the bundle must not get relabeled as belonging to this purchase —
    otherwise a later refund would wrongly revoke access they earned another
    way."""
    author = await _user(db)
    student = await _user(db)
    path = await _path(db, author=author)
    c1, c2 = await _course(db, author=author), await _course(db, author=author)
    await _step(db, path=path, course=c1, position=1)
    await _step(db, path=path, course=c2, position=2)
    pre_existing = Enrollment(
        id=uuid.uuid4(), user_id=student.id, course_id=c1.id, source="self", status="active",
    )
    db.add(pre_existing)
    await db.flush()
    purchase = Purchase(
        id=uuid.uuid4(), user_id=student.id, product_type="learning_path", learning_path_id=path.id,
        amount_cents=path.price_cents, currency=path.currency, status="pending",
    )
    db.add(purchase)
    await db.commit()

    await fulfill(db, _session_obj(purchase_id=purchase.id))
    await db.commit()

    await db.refresh(pre_existing)
    assert pre_existing.purchase_id is None  # untouched — not this purchase's to revoke

    new_enrollment = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id, Enrollment.course_id == c2.id)
    )).scalars().first()
    assert new_enrollment.purchase_id == purchase.id


# ── refund revocation scoped to Enrollment.purchase_id ────────────────────────

@pytest.mark.asyncio
async def test_refund_of_bundle_revokes_only_its_own_enrollments(db, client, monkeypatch):
    author = await _user(db)
    student = await _user(db)
    path = await _path(db, author=author)
    c1, c2 = await _course(db, author=author), await _course(db, author=author)
    await _step(db, path=path, course=c1, position=1)
    await _step(db, path=path, course=c2, position=2)
    pre_existing = Enrollment(
        id=uuid.uuid4(), user_id=student.id, course_id=c1.id, source="self", status="active",
    )
    db.add(pre_existing)
    await db.flush()
    purchase = Purchase(
        id=uuid.uuid4(), user_id=student.id, product_type="learning_path", learning_path_id=path.id,
        amount_cents=path.price_cents, currency=path.currency, status="pending",
        stripe_payment_intent_id="pi_bundle_refund_1",
    )
    db.add(purchase)
    await db.commit()

    await fulfill(db, _session_obj(purchase_id=purchase.id, payment_intent="pi_bundle_refund_1"))
    await db.commit()

    def _mock_construct_event(event):
        monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **kw: event)

    charge = types.SimpleNamespace(
        id="ch_bundle_1", refunded=True, payment_intent="pi_bundle_refund_1", amount_refunded=path.price_cents,
    )
    _mock_construct_event(types.SimpleNamespace(type="charge.refunded", data=types.SimpleNamespace(object=charge)))

    resp = await client.post("/lms/webhooks/stripe", content=b"{}", headers={"stripe-signature": "test-sig"})
    assert resp.status_code == 200, resp.text

    await db.refresh(purchase)
    assert purchase.status == "refunded"

    await db.refresh(pre_existing)
    assert pre_existing.status == "active"  # never touched by this purchase's refund

    revoked = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == student.id, Enrollment.course_id == c2.id)
    )).scalars().first()
    assert revoked.status == "inactive"
