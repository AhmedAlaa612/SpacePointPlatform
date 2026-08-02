"""The fulfilment queue over HTTP (I3-1).

The guard is the point of these. This is the third thing a storekeeper can
do, and it has to be reachable by that role while everything under
`/inventory/kits` stays closed to it — which is why these endpoints live
under `/inventory/fulfilment` instead. Redis-free.
"""

import uuid

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.inventory import Item, Kit, KitItem, KitTemplate, Location, StockLevel, Warehouse
from app.models.inventory.kit_template import KitTemplateItem
from app.models.user import User


async def _user(db, *roles: str) -> User:
    u = User(
        id=uuid.uuid4(), full_name=f"P{uuid.uuid4().hex[:4]}",
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"), roles=list(roles), status="active",
    )
    db.add(u)
    await db.flush()
    return u


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _short_kit(db, *, present=3, required=5, stock=10):
    loc = Location(id=uuid.uuid4(), name=f"W{uuid.uuid4().hex[:4]}", country="AE")
    db.add(loc)
    await db.flush()
    wh = Warehouse(id=uuid.uuid4(), location_id=loc.id, name=f"{loc.name} Main")
    db.add(wh)
    await db.flush()
    item = Item(
        id=uuid.uuid4(), name=f"MPU {uuid.uuid4().hex[:4]}", category="board",
        returnable_default=False,
    )
    db.add(item)
    await db.flush()
    tpl = KitTemplate(id=uuid.uuid4(), name="SatKit", code=f"T{uuid.uuid4().hex[:5]}")
    db.add(tpl)
    await db.flush()
    db.add(KitTemplateItem(
        id=uuid.uuid4(), template_id=tpl.id, item_id=item.id, required_qty=required
    ))
    kit = Kit(
        id=uuid.uuid4(), template_id=tpl.id, label=f"SP-K-{uuid.uuid4().hex[:6]}",
        public_token=uuid.uuid4().hex * 2, current_location_id=loc.id,
        current_warehouse_id=wh.id,
    )
    db.add(kit)
    await db.flush()
    if present:
        db.add(KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=item.id, qty=present))
    if stock:
        db.add(StockLevel(id=uuid.uuid4(), item_id=item.id, warehouse_id=wh.id, qty=stock))
    await db.flush()
    return kit, item, loc


@pytest.mark.asyncio
async def test_a_storekeeper_can_see_the_queue_and_close_a_line(client, db):
    keeper = await _user(db, "storekeeper")
    kit, item, _loc = await _short_kit(db)

    r = await client.get("/inventory/fulfilment", headers=_headers(keeper))
    assert r.status_code == 200
    [row] = [x for x in r.json() if x["kit_id"] == str(kit.id)]
    assert row["shortages"][0]["short_by"] == 2
    assert row["shortages"][0]["available"] == 10
    assert row["fixable_now"] == 1

    r = await client.post(
        f"/inventory/fulfilment/{kit.id}/fulfil",
        json={"lines": [{"item_id": str(item.id), "qty": 2}]},
        headers=_headers(keeper),
    )
    assert r.status_code == 201
    assert r.json()[0]["reason"] == "refill"

    r = await client.get("/inventory/fulfilment", headers=_headers(keeper))
    assert [x for x in r.json() if x["kit_id"] == str(kit.id)] == []


@pytest.mark.asyncio
async def test_operations_reaches_it_too(client, db):
    """`require_storekeeper` admits both — ops restocks as well, and the
    storekeeper's narrowness is about what they *cannot* reach, not about
    fulfilment being exclusive to them."""
    ops = await _user(db, "operations")
    kit, _item, _loc = await _short_kit(db)

    r = await client.get("/inventory/fulfilment", headers=_headers(ops))
    assert r.status_code == 200
    assert any(x["kit_id"] == str(kit.id) for x in r.json())


@pytest.mark.asyncio
async def test_an_instructor_cannot_see_the_queue(client, db):
    """The fleet is not browsable by the people who carry it — same rule as
    `/inventory/kits` returning 403 for an instructor."""
    instructor = await _user(db, "instructor")
    r = await client.get("/inventory/fulfilment", headers=_headers(instructor))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_the_storekeeper_still_cannot_reach_the_kits_namespace(client, db):
    """This is why fulfilment lives under its own prefix. Adding a
    storekeeper-writable route inside `/inventory/kits` would make that
    boundary a per-route question instead of one you can read off the URL."""
    keeper = await _user(db, "storekeeper")
    kit, _item, _loc = await _short_kit(db)

    assert (await client.get("/inventory/kits", headers=_headers(keeper))).status_code == 403
    assert (await client.get(
        f"/inventory/kits/{kit.id}", headers=_headers(keeper)
    )).status_code == 403


@pytest.mark.asyncio
async def test_flagging_awaiting_parts_and_clearing_it(client, db):
    keeper = await _user(db, "storekeeper")
    kit, item, _loc = await _short_kit(db, stock=0)

    r = await client.put(
        f"/inventory/fulfilment/{kit.id}/awaiting",
        json={"awaiting": True, "note": "none on the shelf"},
        headers=_headers(keeper),
    )
    assert r.status_code == 200
    assert r.json()["awaiting_parts_since"] is not None
    assert r.json()["awaiting_parts_note"] == "none on the shelf"
    assert r.json()["fixable_now"] == 0

    r = await client.put(
        f"/inventory/fulfilment/{kit.id}/awaiting",
        json={"awaiting": False}, headers=_headers(keeper),
    )
    assert r.status_code == 200
    assert r.json()["awaiting_parts_since"] is None


@pytest.mark.asyncio
async def test_fulfilling_beyond_the_shelf_is_a_409_not_a_silent_partial(client, db):
    keeper = await _user(db, "storekeeper")
    kit, item, _loc = await _short_kit(db, present=0, required=5, stock=2)

    r = await client.post(
        f"/inventory/fulfilment/{kit.id}/fulfil",
        json={"lines": [{"item_id": str(item.id), "qty": 5}]},
        headers=_headers(keeper),
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_an_unknown_kit_is_404(client, db):
    keeper = await _user(db, "storekeeper")
    r = await client.post(
        f"/inventory/fulfilment/{uuid.uuid4()}/fulfil",
        json={"lines": [{"item_id": str(uuid.uuid4()), "qty": 1}]},
        headers=_headers(keeper),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_a_storekeeper_can_load_every_page_their_sidebar_offers(client, db):
    """Regression, found in the browser on 2026-07-30 and not by any test.

    A storekeeper's sidebar is deliberately tiny, and from I1-4 until this was
    caught *every call its landing page made returned 403* — `/inventory/stock`,
    `/inventory/overdue` and `/inventory/locations` were all
    `require_operations`. The page rendered "nothing on the shelves yet"
    regardless of what was on them, so the failure was silent.

    I1-4's walkthrough missed it because it was done as an admin, and admin
    passes every guard. If a page is in a role's sidebar, something has to
    load it *as that role*.
    """
    keeper = await _user(db, "storekeeper")
    kit, _item, _loc = await _short_kit(db)

    reachable = [
        await client.get("/inventory/stock", headers=_headers(keeper)),
        await client.get("/inventory/overdue", headers=_headers(keeper)),
        await client.get("/inventory/locations", headers=_headers(keeper)),
        await client.get("/inventory/fulfilment", headers=_headers(keeper)),
    ]
    assert [r.status_code for r in reachable] == [200] * 4

    # ...and widening those reads must not have opened any of the writes.
    still_shut = [
        await client.post("/inventory/locations", headers=_headers(keeper),
                          json={"name": "Sneaky", "country": "AE"}),
        await client.get("/inventory/items", headers=_headers(keeper)),
        await client.get("/inventory/movements", headers=_headers(keeper)),
        await client.get("/inventory/kits", headers=_headers(keeper)),
    ]
    assert [r.status_code for r in still_shut] == [403] * 4
