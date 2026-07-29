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
from app.models.inventory import Item, Kit, KitTemplate, Location, StockLevel
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


async def _kit(db, loc, tpl, **kw) -> Kit:
    kit = Kit(
        id=uuid.uuid4(), template_id=tpl.id,
        label=f"SP-K-{uuid.uuid4().hex[:6]}", public_token=uuid.uuid4().hex * 2,
        current_location_id=loc.id, **kw,
    )
    db.add(kit)
    await db.flush()
    return kit


# ── catalogue ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_list_a_location(db, client, ops_headers):
    resp = await client.post("/inventory/locations", headers=ops_headers,
                             json={"name": "Al Ain", "country": "ae"})
    assert resp.status_code == 201, resp.text
    assert resp.json()["country"] == "AE", "country is normalised to upper case"

    listed = await client.get("/inventory/locations", headers=ops_headers)
    assert "Al Ain" in [loc["name"] for loc in listed.json()]


@pytest.mark.asyncio
async def test_a_location_holding_kits_cannot_be_deactivated(db, client, ops_headers):
    loc = await _location(db)
    tpl = await _template(db)
    await _kit(db, loc, tpl)
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
    screw = await _item(db, name="M3 Screw", is_consumable=True)
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
    tpl = await _template(db)
    board = await _item(db, name="EPS Board")
    await db.commit()
    await client.put(f"/inventory/templates/{tpl.id}/items", headers=ops_headers,
                     json=[{"item_id": str(board.id), "required_qty": 1}])

    resp = await client.post("/inventory/kits/bulk", headers=ops_headers, json={
        "template_id": str(tpl.id), "location_id": str(loc.id), "count": 3, "complete": True,
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
    tpl = await _template(db)
    await db.commit()
    body = {"template_id": str(tpl.id), "location_id": str(loc.id), "count": 2, "complete": False}

    first = await client.post("/inventory/kits/bulk", headers=ops_headers, json=body)
    second = await client.post("/inventory/kits/bulk", headers=ops_headers, json=body)

    labels = [k["label"] for k in first.json()] + [k["label"] for k in second.json()]
    assert labels == [f"SP-{tpl.code}-{n:04d}" for n in (1, 2, 3, 4)]


@pytest.mark.asyncio
async def test_incomplete_kits_report_a_shortage_count(db, client, ops_headers):
    loc = await _location(db)
    tpl = await _template(db)
    board = await _item(db, name="EPS Board")
    await db.commit()
    await client.put(f"/inventory/templates/{tpl.id}/items", headers=ops_headers,
                     json=[{"item_id": str(board.id), "required_qty": 1}])

    await client.post("/inventory/kits/bulk", headers=ops_headers, json={
        "template_id": str(tpl.id), "location_id": str(loc.id), "count": 1, "complete": False,
    })
    listed = await client.get("/inventory/kits", headers=ops_headers)
    assert listed.json()[0]["shortage_count"] == 1


@pytest.mark.asyncio
async def test_kit_labels_are_unique(db, client, ops_headers):
    loc = await _location(db)
    tpl = await _template(db)
    await db.commit()
    body = {"template_id": str(tpl.id), "label": "SP-SATKIT-0001",
            "current_location_id": str(loc.id)}
    assert (await client.post("/inventory/kits", headers=ops_headers, json=body)).status_code == 201
    assert (await client.post("/inventory/kits", headers=ops_headers, json=body)).status_code == 409


@pytest.mark.asyncio
async def test_issuing_then_returning_a_kit_through_the_api(db, client, ops_headers, instructor):
    loc = await _location(db)
    other = await _location(db, name="Abu Dhabi")
    tpl = await _template(db)
    kit = await _kit(db, loc, tpl)
    await db.commit()

    out = await client.post(f"/inventory/kits/{kit.id}/move", headers=ops_headers, json={
        "to_user_id": str(instructor.id), "reason": "issue", "due_back_on": "2026-08-30",
    })
    assert out.status_code == 201, out.text

    detail = (await client.get(f"/inventory/kits/{kit.id}", headers=ops_headers)).json()
    assert detail["current_holder_user_id"] == str(instructor.id)
    assert detail["location_name"] == "Dubai", "still belongs to Dubai while it is out"

    back = await client.post(f"/inventory/kits/{kit.id}/move", headers=ops_headers, json={
        "to_location_id": str(other.id), "reason": "return",
    })
    assert back.status_code == 201
    detail = (await client.get(f"/inventory/kits/{kit.id}", headers=ops_headers)).json()
    assert detail["current_holder_user_id"] is None
    assert detail["location_name"] == "Abu Dhabi"


@pytest.mark.asyncio
async def test_a_kit_move_needs_exactly_one_destination(db, client, ops_headers, instructor):
    loc = await _location(db)
    tpl = await _template(db)
    kit = await _kit(db, loc, tpl)
    await db.commit()

    both = await client.post(f"/inventory/kits/{kit.id}/move", headers=ops_headers, json={
        "to_location_id": str(loc.id), "to_user_id": str(instructor.id),
    })
    neither = await client.post(f"/inventory/kits/{kit.id}/move", headers=ops_headers, json={})
    assert both.status_code == 422
    assert neither.status_code == 422


@pytest.mark.asyncio
async def test_kit_history_includes_what_went_into_it(db, client, ops_headers, keeper_headers):
    loc = await _location(db)
    tpl = await _template(db)
    kit = await _kit(db, loc, tpl)
    mpu = await _item(db, name="MPU")
    db.add(StockLevel(id=uuid.uuid4(), item_id=mpu.id, location_id=loc.id, qty=5))
    await db.commit()

    await client.post("/inventory/stock/move", headers=keeper_headers, json={
        "item_id": str(mpu.id), "qty": 2, "reason": "refill",
        "from_location_id": str(loc.id), "to_kit_id": str(kit.id),
    })

    history = (await client.get(f"/inventory/kits/{kit.id}/movements", headers=ops_headers)).json()
    assert len(history) == 1
    assert history[0]["to_kit_id"] == str(kit.id)


# ── stock ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_refill_moves_stock_into_a_kit(db, client, ops_headers, keeper_headers):
    loc = await _location(db)
    tpl = await _template(db)
    kit = await _kit(db, loc, tpl)
    mpu = await _item(db, name="MPU")
    db.add(StockLevel(id=uuid.uuid4(), item_id=mpu.id, location_id=loc.id, qty=5))
    await db.commit()

    resp = await client.post("/inventory/stock/move", headers=keeper_headers, json={
        "item_id": str(mpu.id), "qty": 2, "reason": "refill",
        "from_location_id": str(loc.id), "to_kit_id": str(kit.id),
    })
    assert resp.status_code == 201, resp.text

    stock = (await client.get("/inventory/stock", headers=ops_headers)).json()
    assert stock[0]["qty"] == 3
    detail = (await client.get(f"/inventory/kits/{kit.id}", headers=ops_headers)).json()
    assert detail["contents"][0]["qty"] == 2


@pytest.mark.asyncio
async def test_stock_cannot_be_moved_below_zero(db, client, keeper_headers):
    loc = await _location(db)
    other = await _location(db, name="Cairo")
    mpu = await _item(db)
    db.add(StockLevel(id=uuid.uuid4(), item_id=mpu.id, location_id=loc.id, qty=1))
    await db.commit()

    resp = await client.post("/inventory/stock/move", headers=keeper_headers, json={
        "item_id": str(mpu.id), "qty": 4, "reason": "transfer",
        "from_location_id": str(loc.id), "to_location_id": str(other.id),
    })
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_adjustment_requires_a_reason(db, client, keeper_headers):
    loc = await _location(db)
    mpu = await _item(db)
    await db.commit()
    resp = await client.post("/inventory/stock/adjust", headers=keeper_headers, json={
        "item_id": str(mpu.id), "location_id": str(loc.id), "new_qty": 3, "reason": "",
    })
    assert resp.status_code == 422, "an empty reason is rejected before it reaches the service"


@pytest.mark.asyncio
async def test_confirmation_is_idempotent_over_the_api(db, client, ops_headers, keeper_headers, instructor):
    loc = await _location(db)
    tpl = await _template(db)
    kit = await _kit(db, loc, tpl)
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
    tpl = await _template(db)
    kit = await _kit(db, loc, tpl)
    await db.commit()

    await client.post(f"/inventory/kits/{kit.id}/move", headers=ops_headers, json={
        "to_user_id": str(instructor.id), "reason": "issue", "due_back_on": "2026-01-01",
    })
    assert len((await client.get("/inventory/overdue", headers=ops_headers)).json()) == 1

    await client.post(f"/inventory/kits/{kit.id}/move", headers=ops_headers, json={
        "to_location_id": str(loc.id), "reason": "return",
    })
    assert (await client.get("/inventory/overdue", headers=ops_headers)).json() == []


# ── the instructor's own kits ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_my_kits_shows_only_what_i_hold(db, client, ops_headers, instructor, instructor_headers):
    loc = await _location(db)
    tpl = await _template(db)
    mine = await _kit(db, loc, tpl, current_holder_user_id=instructor.id)
    await _kit(db, loc, tpl)                       # on the shelf
    someone_else = await _make_user(db, "instructor")
    await _kit(db, loc, tpl, current_holder_user_id=someone_else.id)
    await db.commit()

    resp = await client.get("/inventory/my-kits", headers=instructor_headers)
    assert resp.status_code == 200
    assert [k["id"] for k in resp.json()] == [str(mine.id)]


@pytest.mark.asyncio
async def test_an_instructor_cannot_browse_the_whole_fleet(db, client, instructor_headers):
    resp = await client.get("/inventory/kits", headers=instructor_headers)
    assert resp.status_code == 403


# ── role guards: the storekeeper's negative space ───────────────────────────

@pytest.mark.asyncio
async def test_a_storekeeper_may_restock_and_adjust(db, client, keeper_headers):
    loc = await _location(db)
    mpu = await _item(db)
    await db.commit()
    resp = await client.post("/inventory/stock/adjust", headers=keeper_headers, json={
        "item_id": str(mpu.id), "location_id": str(loc.id), "new_qty": 12, "reason": "delivery",
    })
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_a_storekeeper_cannot_touch_the_catalogue_or_the_kits(db, client, keeper_headers):
    """The reason the role exists. If any of these starts returning 2xx,
    somebody has widened require_operations or pointed an endpoint at the
    wrong guard."""
    loc = await _location(db)
    tpl = await _template(db)
    kit = await _kit(db, loc, tpl)
    await db.commit()

    forbidden = [
        await client.get("/inventory/kits", headers=keeper_headers),
        await client.get(f"/inventory/kits/{kit.id}", headers=keeper_headers),
        await client.post("/inventory/kits", headers=keeper_headers, json={
            "template_id": str(tpl.id), "label": "SP-X-0001", "current_location_id": str(loc.id),
        }),
        await client.post("/inventory/kits/bulk", headers=keeper_headers, json={
            "template_id": str(tpl.id), "location_id": str(loc.id), "count": 1,
        }),
        await client.patch(f"/inventory/kits/{kit.id}", headers=keeper_headers, json={"status": "retired"}),
        await client.post(f"/inventory/kits/{kit.id}/move", headers=keeper_headers, json={
            "to_location_id": str(loc.id),
        }),
        await client.post("/inventory/items", headers=keeper_headers, json={"name": "Sneaky"}),
        await client.post("/inventory/locations", headers=keeper_headers, json={
            "name": "Sneaky", "country": "AE",
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
