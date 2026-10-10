"""Step 7 — Ground Station shop (products, mock checkout, webhook, fulfill).

No STRIPE_SECRET_KEY in tests, so checkout exercises the mock session
path; the webhook settle call uses the unsigned dev shape. Fulfillment
moves linked ledger stock and writes `sold` movements.
"""

import uuid

import pytest
from sqlalchemy import delete, select

from app.core.security import create_access_token, get_password_hash
from app.models.inventory.movement import Movement
from app.models.inventory.shop_item import ShopItem
from app.models.inventory.shop_order import ShopOrder
from app.models.inventory.stock import StockLevel
from app.models.user import User


async def _ensure_tables(db):
    from app.models.inventory.shop_order import ShopOrderItem

    conn = await db.connection()
    for table in (ShopItem.__table__, ShopOrder.__table__, ShopOrderItem.__table__):
        await conn.run_sync(lambda c, t=table: t.create(c, checkfirst=True))


async def _clear(db):
    from app.models.inventory.shop_order import ShopOrderItem

    for model in (ShopOrderItem, ShopOrder, ShopItem):
        await db.execute(delete(model))
    await db.flush()


async def _seed_item(db, **overrides):
    payload = {
        "slug": f"widget-{uuid.uuid4().hex[:6]}",
        "display_name": "Test Widget",
        "price_aed": 20,
        "is_published": True,
    }
    payload.update(overrides)
    row = ShopItem(id=uuid.uuid4(), **payload)
    db.add(row)
    await db.flush()
    return row


async def _make_user(db, roles):
    user = User(
        id=uuid.uuid4(),
        full_name="Test User",
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("pass"),
        roles=roles,
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.roles)}"}


CHECKOUT = {
    "customer_name": "Leia Organa",
    "customer_email": "leia@example.com",
    "shipping_address": {"street": "1 Rebel Base", "city": "Dubai", "emirate": "Dubai", "country": "AE"},
    "success_url": "https://example.com/success",
    "cancel_url": "https://example.com/cancel",
}


def _use_mock_stripe(monkeypatch):
    """Deterministic dev path regardless of local Stripe credentials."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "")
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")


@pytest.mark.asyncio
async def test_public_products_and_checkout_flow(db, client, monkeypatch):
    _use_mock_stripe(monkeypatch)
    await _ensure_tables(db)
    await _clear(db)

    assert (await client.get("/public/shop/products")).json() == []

    item = await _seed_item(db, slug="keychain", display_name="Key Chain", price_aed=20)
    await _seed_item(db, slug="hidden-gem", display_name="Hidden Gem", is_published=False)

    products = (await client.get("/public/shop/products")).json()
    assert [p["slug"] for p in products] == ["keychain"]
    assert products[0]["price_aed"] == 20
    assert products[0]["stock_status"] == "pre_order"
    assert products[0]["total_stock"] == 0

    single = await client.get("/public/shop/products/keychain")
    assert single.status_code == 200, single.text
    assert single.json()["display_name"] == "Key Chain"
    assert (await client.get("/public/shop/products/nope")).status_code == 404
    assert (await client.get("/public/shop/products/hidden-gem")).status_code == 404

    # Checkout resolves by slug; unknown or unpublished items 404
    bad = await client.post(
        "/public/shop/checkout",
        json={**CHECKOUT, "items": [{"shop_item_id": "nope", "quantity": 1}]},
    )
    assert bad.status_code == 404
    bad = await client.post(
        "/public/shop/checkout",
        json={**CHECKOUT, "items": [{"shop_item_id": "hidden-gem", "quantity": 1}]},
    )
    assert bad.status_code == 404

    resp = await client.post(
        "/public/shop/checkout",
        json={**CHECKOUT, "items": [{"shop_item_id": "keychain", "quantity": 2}]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["checkout_url"].startswith("https://example.com/success?session_id=mock_cs_")
    assert body["order_number"].startswith("SP-")

    # Order persisted pending_payment with priced snapshot lines
    order = (
        await db.execute(select(ShopOrder).where(ShopOrder.id == body["order_id"]))
    ).scalars().one()
    assert order.status == "pending_payment"
    assert float(order.total_amount_aed) == 40
    assert len(order.items) == 1
    assert order.items[0].item_name == "Key Chain"
    assert float(order.items[0].unit_price_aed) == 20

    # Webhook settles → paid; replay is idempotent
    hook = await client.post("/public/shop/webhook", json={"session_id": order.stripe_checkout_session_id})
    assert hook.status_code == 200, hook.text
    assert hook.json()["status"] == "paid"
    hook = await client.post("/public/shop/webhook", json={"session_id": order.stripe_checkout_session_id})
    assert hook.json()["status"] == "paid"
    assert (await client.post("/public/shop/webhook", json={"session_id": "mock_cs_missing"})).status_code == 404
    assert (await client.post("/public/shop/webhook", json={})).status_code == 400

    # Fulfillment requires paid (fresh pending order cannot skip ahead)...
    resp2 = await client.post(
        "/public/shop/checkout",
        json={**CHECKOUT, "items": [{"shop_item_id": str(item.id), "quantity": 1}]},
    )
    pending_id = resp2.json()["order_id"]
    admin = await _make_user(db, ["admin"])
    denied = await client.post(f"/admin/shop/orders/{pending_id}/fulfill", json={}, headers=_headers(admin))
    assert denied.status_code == 400

    # ...and writes ledger movements for stocked lines
    from app.models.inventory.item import Item
    from app.models.inventory.location import Location
    from app.models.inventory.warehouse import Warehouse

    location = Location(id=uuid.uuid4(), name="Test Location", country="AE")
    db.add(location)
    await db.flush()
    warehouse = Warehouse(id=uuid.uuid4(), location_id=location.id, name="Test Warehouse")
    db.add(warehouse)
    await db.flush()
    catalog = Item(id=uuid.uuid4(), name=f"Catalog Widget {uuid.uuid4().hex[:6]}", category="merch")
    db.add(catalog)
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=catalog.id, warehouse_id=warehouse.id, qty=5))
    await db.flush()

    stocked = await _seed_item(db, slug="stocked", display_name="Stocked", price_aed=10)
    stocked.item_id = catalog.id
    await db.flush()
    resp3 = await client.post(
        "/public/shop/checkout",
        json={**CHECKOUT, "items": [{"shop_item_id": "stocked", "quantity": 2}]},
    )
    paid_id = resp3.json()["order_id"]
    paid_order = await db.get(ShopOrder, paid_id)
    paid_order.status = "paid"
    await db.flush()

    done = await client.post(
        f"/admin/shop/orders/{paid_id}/fulfill",
        json={"warehouse_id": str(warehouse.id), "notes": "Packed"},
        headers=_headers(admin),
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "fulfilled"
    assert done.json()["fulfilled_warehouse_id"] == str(warehouse.id)

    level = (
        await db.execute(
            select(StockLevel).where(
                StockLevel.item_id == catalog.id, StockLevel.warehouse_id == warehouse.id
            )
        )
    ).scalars().one()
    assert level.qty == 3
    moves = (
        await db.execute(
            select(Movement).where(
                Movement.item_id == catalog.id, Movement.reason == "sold"
            )
        )
    ).scalars().all()
    assert len(moves) == 1 and moves[0].qty == 2


@pytest.mark.asyncio
async def test_shop_admin_guards_and_orders(db, client, monkeypatch):
    _use_mock_stripe(monkeypatch)
    await _ensure_tables(db)
    await _clear(db)
    admin = await _make_user(db, ["admin"])
    student = await _make_user(db, ["student"])

    assert (await client.get("/admin/shop/items")).status_code in (401, 403)
    assert (await client.get("/admin/shop/orders")).status_code in (401, 403)
    assert (await client.get("/admin/shop/items", headers=_headers(student))).status_code == 403

    created = (
        await client.post(
            "/admin/shop/items",
            json={"slug": "cap", "display_name": "Cap", "price_aed": 75, "is_published": True},
            headers=_headers(admin),
        )
    ).json()
    assert created["is_preorder_enabled"] is True

    dup = await client.post(
        "/admin/shop/items",
        json={"slug": "cap", "display_name": "Cap 2", "price_aed": 80},
        headers=_headers(admin),
    )
    assert dup.status_code == 409

    updated = (
        await client.put(
            f"/admin/shop/items/{created['id']}",
            json={"price_aed": 70, "is_published": False},
            headers=_headers(admin),
        )
    ).json()
    assert updated["price_aed"] == 70
    assert (await client.get("/public/shop/products")).json() == []

    orders = (await client.get("/admin/shop/orders", headers=_headers(admin))).json()
    assert orders == []
    filtered = (
        await client.get("/admin/shop/orders", params={"status": "bogus"}, headers=_headers(admin))
    )
    assert filtered.status_code == 400

    assert (
        await client.delete(f"/admin/shop/items/{created['id']}", headers=_headers(admin))
    ).status_code == 204
    assert (
        await client.delete(f"/admin/shop/items/{uuid.uuid4()}", headers=_headers(admin))
    ).status_code == 404
