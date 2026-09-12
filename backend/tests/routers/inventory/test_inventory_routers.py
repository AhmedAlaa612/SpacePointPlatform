"""Endpoint tests for /inventory/* (I1-3).

Uses the shared Redis-free `client` from tests/conftest.py — nothing here
enqueues anything, so none of it needs a broker.

The role-guard tests carry the most weight: `storekeeper` is defined by what
it *cannot* reach, and that restriction is invisible negative space (it falls
out of `require_operations` not listing the role). If a later change widens
it, these are what fail.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.inventory import City, Item, Kit, KitTemplate, KitTemplateItem, Location, StockLevel, Warehouse
from app.models.user import User


# ── fixtures ────────────────────────────────────────────────────────────────

async def _make_user(db, *roles: str) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name=f"{roles[0].title()} Person",
        email=f"{roles[0]}-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"),
        roles=list(roles),
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.fixture
async def ops(db):
    return await _make_user(db, "operations")


@pytest.fixture
async def ops_headers(ops):
    return _headers(ops)


@pytest.fixture
async def keeper(db):
    return await _make_user(db, "storekeeper")


@pytest.fixture
async def keeper_headers(keeper):
    return _headers(keeper)


@pytest.fixture
async def coo(db):
    return await _make_user(db, "coo")


@pytest.fixture
async def coo_headers(coo):
    return _headers(coo)


@pytest.fixture
async def instructor(db):
    return await _make_user(db, "instructor")


@pytest.fixture
async def instructor_headers(instructor):
    return _headers(instructor)


@pytest.fixture
async def admin(db):
    return await _make_user(db, "admin")


@pytest.fixture
async def admin_headers(admin):
    return _headers(admin)


async def _location(db, name="Dubai") -> Location:
    loc = Location(id=uuid.uuid4(), name=name, country="AE")
    db.add(loc)
    await db.flush()
    return loc


async def _warehouse(db, loc, name=None) -> Warehouse:
    wh = Warehouse(id=uuid.uuid4(), location_id=loc.id, name=name or f"{loc.name} Main")
    db.add(wh)
    await db.flush()
    return wh


async def _item(db, name=None, **kw) -> Item:
    item = Item(id=uuid.uuid4(), name=name or f"Item {uuid.uuid4().hex[:6]}", **kw)
    db.add(item)
    await db.flush()
    return item


async def _template(db, code="SATKIT") -> KitTemplate:
    tpl = KitTemplate(id=uuid.uuid4(), name="SatKit v1", code=f"{code}{uuid.uuid4().hex[:4].upper()}")
    db.add(tpl)
    await db.flush()
    return tpl


async def _kit(db, wh, tpl, **kw) -> Kit:
    kit = Kit(
        id=uuid.uuid4(), template_id=tpl.id,
        label=f"SP-K-{uuid.uuid4().hex[:6]}", public_token=uuid.uuid4().hex * 2,
        current_location_id=wh.location_id, current_warehouse_id=wh.id, **kw,
    )
    db.add(kit)
    await db.flush()
    return kit


# ── catalogue ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_list_a_location(db, client, ops_headers):
    city = City(id=uuid.uuid4(), name=f"Al Ain {uuid.uuid4().hex[:6]}", country="AE")
    db.add(city)
    await db.commit()

    resp = await client.post("/inventory/locations", headers=ops_headers,
                             json={"name": "Al Ain", "city_id": str(city.id)})
    assert resp.status_code == 201, resp.text
    # The country is never entered — it is derived from the city.
    assert resp.json()["country"] == "AE"
    assert resp.json()["city_id"] == str(city.id)

    listed = await client.get("/inventory/locations", headers=ops_headers)
    assert "Al Ain" in [loc["name"] for loc in listed.json()]


@pytest.mark.asyncio
async def test_create_location_rejects_an_unknown_city(db, client, ops_headers):
    resp = await client.post("/inventory/locations", headers=ops_headers,
                             json={"name": "Won't Land", "city_id": str(uuid.uuid4())})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_location_does_not_auto_create_a_warehouse(db, client, ops_headers):
    """Decoupled 2026-08-08 (operator request) — a location used to always
    get a default "{Name} Warehouse" in the same transaction; now creating
    one is a fully separate, manual POST /inventory/warehouses step."""
    before = len((await db.execute(select(Warehouse))).scalars().all())
    city = City(id=uuid.uuid4(), name=f"Fujairah {uuid.uuid4().hex[:6]}", country="AE")
    db.add(city)
    await db.commit()

    resp = await client.post("/inventory/locations", headers=ops_headers,
                             json={"name": "Fujairah Depot", "city_id": str(city.id)})
    assert resp.status_code == 201, resp.text
    location_id = resp.json()["id"]

    after = len((await db.execute(select(Warehouse))).scalars().all())
    assert after == before, "no warehouse should have been created"

    warehouses_here = (await db.execute(
        select(Warehouse).where(Warehouse.location_id == uuid.UUID(location_id))
    )).scalars().all()
    assert warehouses_here == []


@pytest.mark.asyncio
async def test_location_city_id_round_trips_with_resolved_name(db, client, ops_headers):
    city = City(id=uuid.uuid4(), name=f"Testville {uuid.uuid4().hex[:6]}", country="AE")
    db.add(city)
    await db.commit()

    created = await client.post("/inventory/locations", headers=ops_headers,
                                json={"name": "City-Linked Hub", "country": "ae", "city_id": str(city.id)})
    assert created.status_code == 201, created.text
    assert created.json()["city_id"] == str(city.id)
    assert created.json()["city_name"] == city.name

    listed = await client.get("/inventory/locations", headers=ops_headers)
    match = next(loc for loc in listed.json() if loc["name"] == "City-Linked Hub")
    assert match["city_name"] == city.name


@pytest.mark.asyncio
async def test_city_crud(db, client, ops_headers, keeper_headers):
    name = f"Testopolis {uuid.uuid4().hex[:6]}"
    created = await client.post("/inventory/cities", headers=ops_headers,
                                json={"name": name, "country": "ae"})
    assert created.status_code == 201, created.text
    assert created.json()["country"] == "AE"
    city_id = created.json()["id"]

    # storekeeper can read (same reasoning as locations — naming a city is
    # a precondition of storekeeper work once locations reference one)
    listed = await client.get("/inventory/cities", headers=keeper_headers)
    assert listed.status_code == 200
    assert name in [c["name"] for c in listed.json()]

    updated = await client.patch(f"/inventory/cities/{city_id}", headers=ops_headers, json={"is_active": False})
    assert updated.status_code == 200
    assert updated.json()["is_active"] is False

    active_only = await client.get("/inventory/cities", headers=keeper_headers)
    assert city_id not in [c["id"] for c in active_only.json()]


@pytest.mark.asyncio
async def test_a_location_holding_kits_cannot_be_deactivated(db, client, ops_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    await _kit(db, wh, tpl)
    await db.commit()

    resp = await client.patch(f"/inventory/locations/{loc.id}", headers=ops_headers,
                              json={"is_active": False})
    assert resp.status_code == 409
    assert "still sit here" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_item_names_are_unique_case_insensitively(db, client, ops_headers):
    await client.post("/inventory/items", headers=ops_headers, json={"name": "EPS Board"})
    dupe = await client.post("/inventory/items", headers=ops_headers, json={"name": "eps board"})
    assert dupe.status_code == 409


@pytest.mark.asyncio
async def test_variant_group_and_label_round_trip(db, client, ops_headers):
    resp = await client.post("/inventory/items", headers=ops_headers, json={
        "name": "T-Shirt L", "category": "other", "variant_group": "T-Shirt", "variant_label": "L",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["variant_group"] == "T-Shirt"
    assert body["variant_label"] == "L"


@pytest.mark.asyncio
async def test_variant_label_is_blank_without_a_group(db, client, ops_headers):
    """A label means nothing without a group to browse it under."""
    resp = await client.post("/inventory/items", headers=ops_headers, json={
        "name": "Lone Item", "category": "other", "variant_label": "L",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["variant_group"] is None
    assert resp.json()["variant_label"] is None


@pytest.mark.asyncio
async def test_clearing_the_variant_group_clears_the_label_too(db, client, ops_headers):
    item = await _item(db, name="T-Shirt M")
    item.variant_group = "T-Shirt"
    item.variant_label = "M"
    await db.commit()

    resp = await client.patch(f"/inventory/items/{item.id}", headers=ops_headers, json={"variant_group": ""})
    assert resp.status_code == 200, resp.text
    assert resp.json()["variant_group"] is None
    assert resp.json()["variant_label"] is None


@pytest.mark.asyncio
async def test_admin_can_destructively_delete_item_with_history_and_usages(db, client, ops_headers, admin_headers):
    tpl = await _template(db)
    item = await _item(db)
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    # Add movement and stock
    await client.post(
        "/inventory/movements",
        headers=ops_headers,
        json={
            "type": "receipt",
            "item_id": str(item.id),
            "warehouse_id": str(wh.id),
            "qty": 5,
            "notes": "Initial stock batch",
        },
    )
    # Put item in template BOM
    await client.put(
        f"/inventory/templates/{tpl.id}/items",
        headers=ops_headers,
        json=[{"item_id": str(item.id), "required_qty": 1}],
    )

    # Ops cannot delete (403 forbidden)
    resp_ops = await client.delete(f"/inventory/items/{item.id}", headers=ops_headers)
    assert resp_ops.status_code == 403

    # Admin destructively deletes the item along with all history, stock, and template usages
    resp_admin = await client.delete(f"/inventory/items/{item.id}", headers=admin_headers)
    assert resp_admin.status_code == 204

    # Verify item is gone
    get_res = await client.get("/inventory/items", headers=ops_headers)
    items = get_res.json()
    assert not any(i["id"] == str(item.id) for i in items)

    # Verify template line is gone
    tpl_res = await client.get(f"/inventory/templates/{tpl.id}", headers=ops_headers)
    assert not any(line["item_id"] == str(item.id) for line in tpl_res.json()["items"])

    # Verify stock level is gone
    stock_res = await client.get(f"/inventory/stock?warehouse_id={wh.id}", headers=ops_headers)
    assert not any(s["item_id"] == str(item.id) for s in stock_res.json())


@pytest.mark.asyncio
async def test_admin_can_delete_unused_item(db, client, ops_headers, admin_headers, keeper_headers):
    item = await _item(db, name="Accidental Duplicate Component")
    await db.commit()

    # Storekeeper and ops cannot delete (403 forbidden)
    assert (await client.delete(f"/inventory/items/{item.id}", headers=keeper_headers)).status_code == 403
    assert (await client.delete(f"/inventory/items/{item.id}", headers=ops_headers)).status_code == 403

    # An admin account with active role switched to 'operations' is rejected
    admin_as_ops = {**admin_headers, "X-Active-Role": "operations"}
    assert (await client.delete(f"/inventory/items/{item.id}", headers=admin_as_ops)).status_code == 403

    # Only admin acting as admin can delete
    admin_as_admin = {**admin_headers, "X-Active-Role": "admin"}
    res_admin = await client.delete(f"/inventory/items/{item.id}", headers=admin_as_admin)
    assert res_admin.status_code == 204

    # Verify item is gone
    get_res = await client.get("/inventory/items", headers=ops_headers)
    items = get_res.json()
    assert not any(i["id"] == str(item.id) for i in items)


@pytest.mark.asyncio
async def test_setting_a_template_bom_replaces_it_wholesale(db, client, ops_headers):
    tpl = await _template(db)
    board = await _item(db, name="ADCS Board")
    screw = await _item(db, name="M3 Screw")
    await db.commit()

    first = await client.put(f"/inventory/templates/{tpl.id}/items", headers=ops_headers, json=[
        {"item_id": str(board.id), "required_qty": 1},
        {"item_id": str(screw.id), "required_qty": 20},
    ])
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2

    second = await client.put(f"/inventory/templates/{tpl.id}/items", headers=ops_headers, json=[
        {"item_id": str(board.id), "required_qty": 2},
    ])
    assert [(i["item_name"], i["required_qty"]) for i in second.json()["items"]] == [("ADCS Board", 2)]


@pytest.mark.asyncio
async def test_a_template_cannot_list_the_same_item_twice(db, client, ops_headers):
    tpl = await _template(db)
    item = await _item(db)
    await db.commit()
    resp = await client.put(f"/inventory/templates/{tpl.id}/items", headers=ops_headers, json=[
        {"item_id": str(item.id), "required_qty": 1},
        {"item_id": str(item.id), "required_qty": 2},
    ])
    assert resp.status_code == 400


# ── kits ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bulk_create_numbers_kits_and_fills_them_from_the_template(db, client, ops_headers):
    """The first-day path. Twenty kits, complete, in one call."""
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    board = await _item(db, name="EPS Board")
    await db.commit()
    await client.put(f"/inventory/templates/{tpl.id}/items", headers=ops_headers,
                     json=[{"item_id": str(board.id), "required_qty": 1}])

    resp = await client.post("/inventory/kits/bulk", headers=ops_headers, json={
        "template_id": str(tpl.id), "warehouse_id": str(wh.id), "count": 3, "complete": True,
    })
    assert resp.status_code == 201, resp.text
    kits = resp.json()
    assert [k["label"] for k in kits] == [
        f"SP-{tpl.code}-0001", f"SP-{tpl.code}-0002", f"SP-{tpl.code}-0003",
    ]
    assert all(k["shortage_count"] == 0 for k in kits), "complete=True means no shortages"


@pytest.mark.asyncio
async def test_bulk_create_continues_numbering_rather_than_colliding(db, client, ops_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    await db.commit()
    body = {"template_id": str(tpl.id), "warehouse_id": str(wh.id), "count": 2, "complete": False}

    first = await client.post("/inventory/kits/bulk", headers=ops_headers, json=body)
    second = await client.post("/inventory/kits/bulk", headers=ops_headers, json=body)

    labels = [k["label"] for k in first.json()] + [k["label"] for k in second.json()]
    assert labels == [f"SP-{tpl.code}-{n:04d}" for n in (1, 2, 3, 4)]


@pytest.mark.asyncio
async def test_incomplete_kits_report_a_shortage_count(db, client, ops_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    board = await _item(db, name="EPS Board")
    await db.commit()
    await client.put(f"/inventory/templates/{tpl.id}/items", headers=ops_headers,
                     json=[{"item_id": str(board.id), "required_qty": 1}])

    await client.post("/inventory/kits/bulk", headers=ops_headers, json={
        "template_id": str(tpl.id), "warehouse_id": str(wh.id), "count": 1, "complete": False,
    })
    listed = await client.get("/inventory/kits", headers=ops_headers)
    assert listed.json()[0]["shortage_count"] == 1


@pytest.mark.asyncio
async def test_create_kit_complete_seeds_contents_via_receive_movements(db, client, ops_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    mpu = await _item(db, name="MPU")
    db.add(KitTemplateItem(id=uuid.uuid4(), template_id=tpl.id, item_id=mpu.id, required_qty=3))
    await db.commit()

    resp = await client.post("/inventory/kits", headers=ops_headers, json={
        "template_id": str(tpl.id), "label": "SP-COMPLETE-0001",
        "current_warehouse_id": str(wh.id), "complete": True,
    })
    assert resp.status_code == 201, resp.text
    detail = resp.json()
    assert detail["contents"] == [{"item_id": str(mpu.id), "item_name": "MPU", "qty": 3}]
    assert detail["shortages"] == []

    movements = (await client.get(f"/inventory/kits/{detail['id']}/movements", headers=ops_headers)).json()
    assert len(movements) == 1
    assert movements[0]["reason"] == "receive"
    assert movements[0]["from_warehouse_id"] is None, "arrived complete — nothing came off any shelf"

    stock = (await client.get("/inventory/stock", headers=ops_headers)).json()
    assert stock == [], "receiving straight into a kit must not touch stock_levels"


@pytest.mark.asyncio
async def test_kit_labels_are_unique(db, client, ops_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    await db.commit()
    body = {"template_id": str(tpl.id), "label": "SP-SATKIT-0001",
            "current_warehouse_id": str(wh.id)}
    assert (await client.post("/inventory/kits", headers=ops_headers, json=body)).status_code == 201
    assert (await client.post("/inventory/kits", headers=ops_headers, json=body)).status_code == 409


@pytest.mark.asyncio
async def test_issuing_then_returning_a_kit_through_the_api(db, client, ops_headers, instructor):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    other = await _location(db, name="Abu Dhabi")
    other_wh = await _warehouse(db, other)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    await db.commit()

    out = await client.post(f"/inventory/kits/{kit.id}/move", headers=ops_headers, json={
        "to_user_id": str(instructor.id), "reason": "issue", "due_back_on": "2026-08-30",
    })
    assert out.status_code == 201, out.text

    detail = (await client.get(f"/inventory/kits/{kit.id}", headers=ops_headers)).json()
    assert detail["current_holder_user_id"] == str(instructor.id)
    assert detail["location_name"] == "Dubai", "still belongs to Dubai while it is out"

    back = await client.post(f"/inventory/kits/{kit.id}/move", headers=ops_headers, json={
        "to_warehouse_id": str(other_wh.id), "reason": "return",
    })
    assert back.status_code == 201
    detail = (await client.get(f"/inventory/kits/{kit.id}", headers=ops_headers)).json()
    assert detail["current_holder_user_id"] is None
    assert detail["location_name"] == "Abu Dhabi"


@pytest.mark.asyncio
async def test_a_kit_move_needs_exactly_one_destination(db, client, ops_headers, instructor):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    await db.commit()

    both = await client.post(f"/inventory/kits/{kit.id}/move", headers=ops_headers, json={
        "to_warehouse_id": str(wh.id), "to_user_id": str(instructor.id),
    })
    neither = await client.post(f"/inventory/kits/{kit.id}/move", headers=ops_headers, json={})
    assert both.status_code == 422
    assert neither.status_code == 422


@pytest.mark.asyncio
async def test_kit_history_includes_what_went_into_it(db, client, ops_headers, keeper_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    mpu = await _item(db, name="MPU")
    db.add(StockLevel(id=uuid.uuid4(), item_id=mpu.id, warehouse_id=wh.id, qty=5))
    await db.commit()

    await client.post("/inventory/stock/move", headers=keeper_headers, json={
        "item_id": str(mpu.id), "qty": 2, "reason": "refill",
        "from_warehouse_id": str(wh.id), "to_kit_id": str(kit.id),
    })

    history = (await client.get(f"/inventory/kits/{kit.id}/movements", headers=ops_headers)).json()
    assert len(history) == 1
    assert history[0]["to_kit_id"] == str(kit.id)


# ── stock ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refill_moves_stock_into_a_kit(db, client, ops_headers, keeper_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    mpu = await _item(db, name="MPU")
    db.add(StockLevel(id=uuid.uuid4(), item_id=mpu.id, warehouse_id=wh.id, qty=5))
    await db.commit()

    resp = await client.post("/inventory/stock/move", headers=keeper_headers, json={
        "item_id": str(mpu.id), "qty": 2, "reason": "refill",
        "from_warehouse_id": str(wh.id), "to_kit_id": str(kit.id),
    })
    assert resp.status_code == 201, resp.text

    stock = (await client.get("/inventory/stock", headers=ops_headers)).json()
    assert stock[0]["qty"] == 3
    detail = (await client.get(f"/inventory/kits/{kit.id}", headers=ops_headers)).json()
    assert detail["contents"][0]["qty"] == 2


@pytest.mark.asyncio
async def test_stock_cannot_be_moved_below_zero(db, client, keeper_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    other = await _location(db, name="Cairo")
    other_wh = await _warehouse(db, other)
    mpu = await _item(db)
    db.add(StockLevel(id=uuid.uuid4(), item_id=mpu.id, warehouse_id=wh.id, qty=1))
    await db.commit()

    resp = await client.post("/inventory/stock/move", headers=keeper_headers, json={
        "item_id": str(mpu.id), "qty": 4, "reason": "transfer",
        "from_warehouse_id": str(wh.id), "to_warehouse_id": str(other_wh.id),
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_adjustment_requires_a_reason(db, client, keeper_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    mpu = await _item(db)
    await db.commit()
    resp = await client.post("/inventory/stock/adjust", headers=keeper_headers, json={
        "item_id": str(mpu.id), "warehouse_id": str(wh.id), "new_qty": 3, "reason": "",
    })
    assert resp.status_code == 422, "an empty reason is rejected before it reaches the service"


@pytest.mark.asyncio
async def test_bulk_adjust_writes_one_movement_per_changed_warehouse(db, client, ops_headers, keeper_headers):
    loc = await _location(db)
    wh1 = await _warehouse(db, loc, name="Main Depot")
    wh2 = await _warehouse(db, loc, name="Workshop Store")
    mpu = await _item(db)
    db.add(StockLevel(id=uuid.uuid4(), item_id=mpu.id, warehouse_id=wh1.id, qty=24))
    await db.commit()

    resp = await client.post("/inventory/stock/adjust-bulk", headers=keeper_headers, json={
        "reason": "Monthly stocktake",
        "levels": [
            {"item_id": str(mpu.id), "warehouse_id": str(wh1.id), "new_qty": 24},  # unchanged — skipped
            {"item_id": str(mpu.id), "warehouse_id": str(wh2.id), "new_qty": 8},   # new row
        ],
    })
    assert resp.status_code == 201, resp.text
    assert len(resp.json()) == 1, "the unchanged line should be skipped, not written or errored"

    stock = {s["warehouse_id"]: s["qty"] for s in (await client.get("/inventory/stock", headers=ops_headers)).json()}
    assert stock[str(wh1.id)] == 24
    assert stock[str(wh2.id)] == 8


@pytest.mark.asyncio
async def test_bulk_adjust_with_nothing_changed_is_a_409(db, client, keeper_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    mpu = await _item(db)
    db.add(StockLevel(id=uuid.uuid4(), item_id=mpu.id, warehouse_id=wh.id, qty=5))
    await db.commit()

    resp = await client.post("/inventory/stock/adjust-bulk", headers=keeper_headers, json={
        "reason": "Stocktake", "levels": [{"item_id": str(mpu.id), "warehouse_id": str(wh.id), "new_qty": 5}],
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_count_kit_receive_with_no_shelf_involved(db, client, ops_headers, keeper_headers):
    """A new kit, built complete, with nothing coming off any shelf."""
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    mpu = await _item(db)
    await db.commit()

    resp = await client.post(f"/inventory/kits/{kit.id}/count", headers=keeper_headers, json={
        "reason": "Arrived complete", "from_shelf": False,
        "lines": [{"item_id": str(mpu.id), "new_qty": 4}],
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()[0]["reason"] == "receive"
    assert resp.json()[0]["from_warehouse_id"] is None

    detail = (await client.get(f"/inventory/kits/{kit.id}", headers=ops_headers)).json()
    assert detail["contents"][0]["qty"] == 4
    stock = await client.get("/inventory/stock", headers=ops_headers)
    assert stock.json() == [], "receiving into a kit with no shelf involved must not touch stock_levels"


@pytest.mark.asyncio
async def test_count_kit_refill_ticked_draws_down_the_shelf(db, client, ops_headers, keeper_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    mpu = await _item(db)
    db.add(StockLevel(id=uuid.uuid4(), item_id=mpu.id, warehouse_id=wh.id, qty=10))
    await db.commit()

    resp = await client.post(f"/inventory/kits/{kit.id}/count", headers=keeper_headers, json={
        "reason": "Stocktake", "from_shelf": True,
        "lines": [{"item_id": str(mpu.id), "new_qty": 3}],
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()[0]["reason"] == "refill"

    stock = (await client.get("/inventory/stock", headers=ops_headers)).json()
    assert stock[0]["qty"] == 7
    detail = (await client.get(f"/inventory/kits/{kit.id}", headers=ops_headers)).json()
    assert detail["contents"][0]["qty"] == 3


@pytest.mark.asyncio
async def test_count_kit_correction_down_with_no_shelf_is_a_writeoff_style_adjust(db, client, ops_headers, keeper_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    mpu = await _item(db)
    await db.commit()

    # arrive at 5, then correct down to 2 with no shelf involved
    await client.post(f"/inventory/kits/{kit.id}/count", headers=keeper_headers, json={
        "reason": "Arrived complete", "from_shelf": False,
        "lines": [{"item_id": str(mpu.id), "new_qty": 5}],
    })
    resp = await client.post(f"/inventory/kits/{kit.id}/count", headers=keeper_headers, json={
        "reason": "Two were broken", "from_shelf": False,
        "lines": [{"item_id": str(mpu.id), "new_qty": 2}],
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()[0]["reason"] == "adjust"
    assert resp.json()[0]["to_warehouse_id"] is None and resp.json()[0]["to_kit_id"] is None

    detail = (await client.get(f"/inventory/kits/{kit.id}", headers=ops_headers)).json()
    assert detail["contents"][0]["qty"] == 2


@pytest.mark.asyncio
async def test_count_kit_with_nothing_changed_is_a_409(db, client, keeper_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    mpu = await _item(db)
    await db.commit()

    resp = await client.post(f"/inventory/kits/{kit.id}/count", headers=keeper_headers, json={
        "reason": "Recount", "from_shelf": False,
        "lines": [{"item_id": str(mpu.id), "new_qty": 0}],
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_confirmation_is_idempotent_over_the_api(db, client, ops_headers, keeper_headers, instructor):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    await db.commit()

    mv = (await client.post(f"/inventory/kits/{kit.id}/move", headers=ops_headers, json={
        "to_user_id": str(instructor.id), "reason": "issue",
    })).json()
    assert mv["confirmed_at"] is None

    first = (await client.post(f"/inventory/movements/{mv['id']}/confirm", headers=keeper_headers)).json()
    second = (await client.post(f"/inventory/movements/{mv['id']}/confirm", headers=keeper_headers)).json()
    assert first["confirmed_at"] is not None
    assert second["confirmed_at"] == first["confirmed_at"]


@pytest.mark.asyncio
async def test_overdue_shows_only_what_is_still_out(db, client, ops_headers, instructor):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    await db.commit()

    await client.post(f"/inventory/kits/{kit.id}/move", headers=ops_headers, json={
        "to_user_id": str(instructor.id), "reason": "issue", "due_back_on": "2026-01-01",
    })
    assert len((await client.get("/inventory/overdue", headers=ops_headers)).json()) == 1

    await client.post(f"/inventory/kits/{kit.id}/move", headers=ops_headers, json={
        "to_warehouse_id": str(wh.id), "reason": "return",
    })
    assert (await client.get("/inventory/overdue", headers=ops_headers)).json() == []


# ── the instructor's own kits ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_my_kits_shows_only_what_i_hold(db, client, ops_headers, instructor, instructor_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    mine = await _kit(db, wh, tpl, current_holder_user_id=instructor.id)
    await _kit(db, wh, tpl)                       # on the shelf
    someone_else = await _make_user(db, "instructor")
    await _kit(db, wh, tpl, current_holder_user_id=someone_else.id)
    await db.commit()

    resp = await client.get("/inventory/my-kits", headers=instructor_headers)
    assert resp.status_code == 200
    assert [k["id"] for k in resp.json()] == [str(mine.id)]


@pytest.mark.asyncio
async def test_an_instructor_cannot_browse_the_whole_fleet(db, client, instructor_headers):
    resp = await client.get("/inventory/kits", headers=instructor_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_holders_lists_people_who_can_carry_equipment(db, client, ops_headers):
    """Its own endpoint rather than /admin/users, which is admin-only — ops
    needs a recipient picker without the whole user-management surface."""
    instructor = await _make_user(db, "instructor")
    facilitator = await _make_user(db, "facilitator")
    intern = await _make_user(db, "intern")
    await db.commit()

    ids = [h["id"] for h in (await client.get("/inventory/holders", headers=ops_headers)).json()]
    assert str(instructor.id) in ids
    assert str(facilitator.id) in ids
    assert str(intern.id) not in ids, "an intern doesn't carry kits"


@pytest.mark.asyncio
async def test_holders_excludes_inactive_accounts(db, client, ops_headers):
    """A departed instructor shouldn't still be offered a kit."""
    gone = await _make_user(db, "instructor")
    gone.status = "inactive"
    await db.commit()

    ids = [h["id"] for h in (await client.get("/inventory/holders", headers=ops_headers)).json()]
    assert str(gone.id) not in ids


# ── role guards: the storekeeper's negative space ───────────────────────────

@pytest.mark.asyncio
async def test_a_storekeeper_may_restock_and_adjust(db, client, keeper_headers):
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    mpu = await _item(db)
    await db.commit()
    resp = await client.post("/inventory/stock/adjust", headers=keeper_headers, json={
        "item_id": str(mpu.id), "warehouse_id": str(wh.id), "new_qty": 12, "reason": "delivery",
    })
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_a_storekeeper_may_count_a_kit(db, client, keeper_headers):
    """The one intentional carve-out from the test below: a storekeeper
    standing in front of an open box can say what's in it, same as they can
    already correct a shelf count."""
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    mpu = await _item(db)
    await db.commit()

    resp = await client.post(f"/inventory/kits/{kit.id}/count", headers=keeper_headers, json={
        "reason": "Arrived complete", "from_shelf": False,
        "lines": [{"item_id": str(mpu.id), "new_qty": 3}],
    })
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_a_storekeeper_may_read_kits_list_detail_and_movements(db, client, keeper_headers):
    """Found live in production (2026-08-27): a storekeeper's Kits page
    rendered completely empty, because these three reads 403'd while the
    sibling stock/locations/warehouses reads they could already reach
    stayed silent about it. Same "read is storekeeper-safe, write isn't"
    shape as GET /locations and GET /warehouses already have — a
    storekeeper who "restocks kits, receives goods and records stock
    movements" cannot do that blind to which kits exist or what already
    happened to them."""
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    await db.commit()

    allowed = [
        await client.get("/inventory/kits", headers=keeper_headers),
        await client.get(f"/inventory/kits/{kit.id}", headers=keeper_headers),
        await client.get(f"/inventory/kits/{kit.id}/movements", headers=keeper_headers),
    ]
    assert [r.status_code for r in allowed] == [200] * len(allowed)


@pytest.mark.asyncio
async def test_a_storekeeper_cannot_touch_the_catalogue_or_the_kits(db, client, keeper_headers):
    """The reason the role exists. If any of these starts returning 2xx,
    somebody has widened require_inventory_manage or pointed an endpoint at
    the wrong guard. (`/kits/{id}/count` is a deliberate exception — see
    test_a_storekeeper_may_count_a_kit above — and reading, as opposed to
    writing, the kits themselves is too — see
    test_a_storekeeper_may_read_kits_list_detail_and_movements.)"""
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    await db.commit()

    forbidden = [
        await client.post("/inventory/kits", headers=keeper_headers, json={
            "template_id": str(tpl.id), "label": "SP-X-0001", "current_warehouse_id": str(wh.id),
        }),
        await client.post("/inventory/kits/bulk", headers=keeper_headers, json={
            "template_id": str(tpl.id), "warehouse_id": str(wh.id), "count": 1,
        }),
        await client.patch(f"/inventory/kits/{kit.id}", headers=keeper_headers, json={"status": "retired"}),
        await client.post(f"/inventory/kits/{kit.id}/move", headers=keeper_headers, json={
            "to_warehouse_id": str(wh.id),
        }),
        await client.post("/inventory/items", headers=keeper_headers, json={"name": "Sneaky"}),
        await client.post("/inventory/locations", headers=keeper_headers, json={
            "name": "Sneaky",
        }),
        await client.post("/inventory/templates", headers=keeper_headers, json={
            "name": "Sneaky", "code": "SNEAK",
        }),
    ]
    assert [r.status_code for r in forbidden] == [403] * len(forbidden)


@pytest.mark.asyncio
async def test_a_coo_can_do_anything_with_the_inventory(db, client, coo_headers):
    """Operator directive, 2026-08-27: "COO alone should be able to do
    anything with the inv if he wants" — and "if I can see a page with my
    role, I can use it," after two live incidents where the frontend routed
    a coo into the full inventory nav while the backend rejected every
    single call it made (coo was in neither require_operations nor
    require_storekeeper). `coo` is now full write parity with `operations`
    within the inventory routers (`require_inventory_manage`), on top of
    the read access `require_storekeeper` already gives it. This is a
    blanket grant, not the real scoped approvals/purchasing workflow the
    operator separately described — that's follow-up work."""
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    item = await _item(db)
    city = City(id=uuid.uuid4(), name=f"COO Test City {uuid.uuid4().hex[:6]}", country="AE")
    db.add(city)
    await db.commit()

    ok = [
        # Reads, across every inventory router.
        await client.get("/inventory/kits", headers=coo_headers),
        await client.get(f"/inventory/kits/{kit.id}", headers=coo_headers),
        await client.get("/inventory/items", headers=coo_headers),
        await client.get("/inventory/templates", headers=coo_headers),
        await client.get("/inventory/stock", headers=coo_headers),
        await client.get("/inventory/movements", headers=coo_headers),
        # Writes — exactly what storekeeper is refused above.
        await client.post("/inventory/kits", headers=coo_headers, json={
            "template_id": str(tpl.id), "label": f"SP-COO-{uuid.uuid4().hex[:6]}",
            "current_warehouse_id": str(wh.id),
        }),
        await client.patch(f"/inventory/kits/{kit.id}", headers=coo_headers, json={"status": "damaged"}),
        await client.post(f"/inventory/kits/{kit.id}/move", headers=coo_headers, json={
            "to_warehouse_id": str(wh.id),
        }),
        await client.patch(f"/inventory/items/{item.id}", headers=coo_headers, json={"notes": "coo edit"}),
        await client.post("/inventory/locations", headers=coo_headers, json={
            "name": "COO Test Location", "city_id": str(city.id),
        }),
        await client.post("/inventory/templates", headers=coo_headers, json={
            "name": "COO Template", "code": f"COOTPL{uuid.uuid4().hex[:4].upper()}",
        }),
    ]
    assert [r.status_code for r in ok] == [200, 200, 200, 200, 200, 200, 201, 200, 201, 200, 201, 201], \
        [(r.status_code, r.text) for r in ok]


@pytest.mark.asyncio
async def test_an_intern_reaches_nothing(db, client):
    intern = await _make_user(db, "intern")
    await db.commit()
    headers = _headers(intern)
    assert (await client.get("/inventory/kits", headers=headers)).status_code == 403
    assert (await client.get("/inventory/stock", headers=headers)).status_code == 403
    assert (await client.get("/inventory/my-kits", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_admin_passes_every_inventory_guard(db, client):
    admin = await _make_user(db, "admin")
    await db.commit()
    headers = _headers(admin)
    assert (await client.get("/inventory/kits", headers=headers)).status_code == 200
    assert (await client.get("/inventory/stock", headers=headers)).status_code == 200
    assert (await client.get("/inventory/overdue", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_category_and_subcategory_lifecycle_and_filtering(db, client, ops_headers):
    # 1. Create a category
    cat_res = await client.post("/inventory/categories", headers=ops_headers, json={"name": "computing"})
    assert cat_res.status_code == 201
    cat = cat_res.json()
    cat_id = cat["id"]

    # 2. Create subcategories under that category
    sub1_res = await client.post(f"/inventory/categories/{cat_id}/subcategories", headers=ops_headers, json={"name": "cpu"})
    assert sub1_res.status_code == 201
    sub1 = sub1_res.json()
    assert sub1["name"] == "cpu"
    assert sub1["category_id"] == cat_id

    sub2_res = await client.post(f"/inventory/categories/{cat_id}/subcategories", headers=ops_headers, json={"name": "memory"})
    assert sub2_res.status_code == 201

    # 3. Clashing subcategory name under same category is rejected
    clash_res = await client.post(f"/inventory/categories/{cat_id}/subcategories", headers=ops_headers, json={"name": "cpu"})
    assert clash_res.status_code == 409

    # 4. Listing categories returns nested subcategories
    cats_res = await client.get("/inventory/categories", headers=ops_headers)
    assert cats_res.status_code == 200
    found_cat = next(c for c in cats_res.json() if c["id"] == cat_id)
    sub_names = [s["name"] for s in found_cat["subcategories"]]
    assert "cpu" in sub_names
    assert "memory" in sub_names

    # 5. Create items: one with subcategory, one with invalid subcategory
    bad_item_res = await client.post("/inventory/items", headers=ops_headers, json={
        "name": "Invalid Item", "category": "computing", "subcategory": "nonexistent"
    })
    assert bad_item_res.status_code == 400

    item1_res = await client.post("/inventory/items", headers=ops_headers, json={
        "name": "ARM Cortex M4", "category": "computing", "subcategory": "cpu"
    })
    assert item1_res.status_code == 201
    item1 = item1_res.json()
    assert item1["subcategory"] == "cpu"

    item2_res = await client.post("/inventory/items", headers=ops_headers, json={
        "name": "16MB Flash", "category": "computing", "subcategory": "memory"
    })
    assert item2_res.status_code == 201

    # 6. Filter items by category and subcategory
    res_cat = await client.get("/inventory/items?category=computing", headers=ops_headers)
    assert len(res_cat.json()) == 2

    res_sub = await client.get("/inventory/items?category=computing&subcategory=cpu", headers=ops_headers)
    assert len(res_sub.json()) == 1
    assert res_sub.json()[0]["name"] == "ARM Cortex M4"

    # 7. Renaming subcategory re-labels items
    sub1_id = sub1["id"]
    rename_res = await client.patch(
        f"/inventory/categories/{cat_id}/subcategories/{sub1_id}",
        headers=ops_headers,
        json={"name": "microcontroller"},
    )
    assert rename_res.status_code == 200

    recheck_item = await client.get(f"/inventory/items?subcategory=microcontroller", headers=ops_headers)
    assert len(recheck_item.json()) == 1
    assert recheck_item.json()[0]["name"] == "ARM Cortex M4"
    assert recheck_item.json()[0]["subcategory"] == "microcontroller"

    # 8. Deleting subcategory in use is refused (409)
    del_blocked = await client.delete(
        f"/inventory/categories/{cat_id}/subcategories/{sub1_id}",
        headers=ops_headers,
    )
    assert del_blocked.status_code == 409

    # 9. Update item to clear subcategory, then delete succeeds
    await client.patch(f"/inventory/items/{item1['id']}", headers=ops_headers, json={"subcategory": None})
    del_ok = await client.delete(
        f"/inventory/categories/{cat_id}/subcategories/{sub1_id}",
        headers=ops_headers,
    )
    assert del_ok.status_code == 204


@pytest.mark.asyncio
async def test_warehouse_cabins_crud_and_item_assignments(db, client, ops_headers, keeper_headers):
    loc = await _location(db, name="Abu Dhabi Hub")
    wh = await _warehouse(db, loc, name="Electronics Lab Depot")
    item_a = await _item(db, name="IMU Sensor Rev3")
    item_b = await _item(db, name="Solar Cell 20W")
    await db.commit()

    # 1. Create cabins with pin coordinates
    res_c1 = await client.post(
        f"/inventory/warehouses/{wh.id}/cabins",
        headers=ops_headers,
        json={
            "name": "Cabin 1",
            "description": "Sensors and boards shelf",
            "pin_x": 25.5,
            "pin_y": 40.0,
            "sort_order": 1,
        },
    )
    assert res_c1.status_code == 201
    c1 = res_c1.json()
    assert c1["name"] == "Cabin 1"
    assert c1["pin_x"] == 25.5
    assert c1["pin_y"] == 40.0

    res_c2 = await client.post(
        f"/inventory/warehouses/{wh.id}/cabins",
        headers=ops_headers,
        json={
            "name": "Cabin 2",
            "description": "Solar & batteries shelf",
            "pin_x": 75.0,
            "pin_y": 60.2,
            "sort_order": 2,
        },
    )
    assert res_c2.status_code == 201
    c2 = res_c2.json()

    # Duplicate cabin name in same warehouse fails
    res_dup = await client.post(
        f"/inventory/warehouses/{wh.id}/cabins",
        headers=ops_headers,
        json={"name": "cabin 1"},
    )
    assert res_dup.status_code == 409

    # 2. List cabins
    list_cabins = await client.get(f"/inventory/warehouses/{wh.id}/cabins", headers=keeper_headers)
    assert list_cabins.status_code == 200
    assert len(list_cabins.json()) == 2

    # 3. Assign item A to Cabin 1 (location only, no qty)
    assign_a = await client.put(
        f"/inventory/warehouses/{wh.id}/items/{item_a.id}/cabins",
        headers=ops_headers,
        json=[{"cabin_id": c1["id"], "notes": "Top tray"}],
    )
    assert assign_a.status_code == 200
    assert len(assign_a.json()) == 1
    assert assign_a.json()[0]["cabin_name"] == "Cabin 1"

    # 4. 1:1 enforced — a second cabin for the same item is rejected
    assign_b_split = await client.put(
        f"/inventory/warehouses/{wh.id}/items/{item_b.id}/cabins",
        headers=ops_headers,
        json=[
            {"cabin_id": c1["id"], "notes": "Ready for kits"},
            {"cabin_id": c2["id"], "notes": "Overflow stock"},
        ],
    )
    assert assign_b_split.status_code == 400

    # 4b. Single assignment works
    assign_b = await client.put(
        f"/inventory/warehouses/{wh.id}/items/{item_b.id}/cabins",
        headers=ops_headers,
        json=[{"cabin_id": c2["id"], "notes": "Overflow stock"}],
    )
    assert assign_b.status_code == 200
    assert len(assign_b.json()) == 1

    # 5. GET /stock exposes the cabin tag; assigning never invents quantity —
    # a freshly assigned but uncounted item gets a zero-qty stock row.
    stock_res = await client.get(f"/inventory/stock?warehouse_id={wh.id}", headers=ops_headers)
    assert stock_res.status_code == 200
    stock_items = stock_res.json()
    stock_a = next(s for s in stock_items if s["item_id"] == str(item_a.id))
    assert stock_a["qty"] == 0
    assert len(stock_a["cabins"]) == 1
    assert stock_a["cabins"][0]["cabin_name"] == "Cabin 1"

    # 5b. Unassigning keeps the stock row (it becomes Unassigned, not deleted)
    await db.execute(
        StockLevel.__table__.update()
        .where(StockLevel.warehouse_id == wh.id, StockLevel.item_id == item_a.id)
        .values(qty=7)
    )
    await db.commit()
    unassign_a = await client.put(
        f"/inventory/warehouses/{wh.id}/items/{item_a.id}/cabins",
        headers=ops_headers,
        json=[],
    )
    assert unassign_a.status_code == 200
    assert unassign_a.json() == []
    stock_res2 = await client.get(f"/inventory/stock?warehouse_id={wh.id}", headers=ops_headers)
    stock_a2 = next(s for s in stock_res2.json() if s["item_id"] == str(item_a.id))
    assert stock_a2["qty"] == 7
    assert stock_a2["cabins"] == []

    # 6. Check cabin item_count is accurate (item A unassigned, item B in Cabin 2)
    c1_check = await client.get(f"/inventory/warehouses/{wh.id}/cabins", headers=keeper_headers)
    cabins_data = {c["name"]: c["item_count"] for c in c1_check.json()}
    assert cabins_data["Cabin 1"] == 0
    assert cabins_data["Cabin 2"] == 1  # item_b

    # 7. Update cabin pin coordinates
    patch_c1 = await client.patch(
        f"/inventory/warehouses/{wh.id}/cabins/{c1['id']}",
        headers=ops_headers,
        json={"pin_x": 30.0, "pin_y": 45.0, "description": "Updated description"},
    )
    assert patch_c1.status_code == 200
    assert patch_c1.json()["pin_x"] == 30.0

    # 8. Delete cabin 2: assignment removed, stock stays (becomes unassigned)
    del_c2 = await client.delete(f"/inventory/warehouses/{wh.id}/cabins/{c2['id']}", headers=ops_headers)
    assert del_c2.status_code == 204
    b_cabins = await client.get(f"/inventory/warehouses/{wh.id}/items/{item_b.id}/cabins", headers=ops_headers)
    assert b_cabins.json() == []

    # 9. Listing warehouses (with include_inactive=True) returns cabins without lazy-load issues
    wh_list = await client.get("/inventory/warehouses?include_inactive=true", headers=ops_headers)
    assert wh_list.status_code == 200
    found_wh = next((w for w in wh_list.json() if w["id"] == str(wh.id)), None)
    assert found_wh is not None
    assert len(found_wh["cabins"]) == 1
    assert found_wh["cabins"][0]["name"] == "Cabin 1"

