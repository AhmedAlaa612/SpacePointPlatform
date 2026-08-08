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
async def instructor(db):
    return await _make_user(db, "instructor")


@pytest.fixture
async def instructor_headers(instructor):
    return _headers(instructor)


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
async def test_an_item_in_use_cannot_be_deleted(db, client, ops_headers):
    tpl = await _template(db)
    item = await _item(db)
    await db.commit()
    await client.put(f"/inventory/templates/{tpl.id}/items", headers=ops_headers,
                     json=[{"item_id": str(item.id), "required_qty": 1}])

    resp = await client.delete(f"/inventory/items/{item.id}", headers=ops_headers)
    assert resp.status_code == 409
    assert "template line" in resp.json()["detail"]


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
async def test_a_storekeeper_cannot_touch_the_catalogue_or_the_kits(db, client, keeper_headers):
    """The reason the role exists. If any of these starts returning 2xx,
    somebody has widened require_operations or pointed an endpoint at the
    wrong guard. (`/kits/{id}/count` is the one deliberate exception — see
    test_a_storekeeper_may_count_a_kit above.)"""
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    tpl = await _template(db)
    kit = await _kit(db, wh, tpl)
    await db.commit()

    forbidden = [
        await client.get("/inventory/kits", headers=keeper_headers),
        await client.get(f"/inventory/kits/{kit.id}", headers=keeper_headers),
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
