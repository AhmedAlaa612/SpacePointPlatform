"""The approval gate (2026-08-27 follow-up to the inventory permissions fix).

Self-contained, same pattern as test_fulfilment_routes.py — its own
`_user`/`_headers` rather than importing fixtures from test_inventory_routers.py.

The thing worth proving here isn't the writes themselves (already covered
in test_inventory_routers.py/test_fulfilment_routes.py) — it's that turning
a policy on changes *only* whether the write happens immediately or waits,
never who can call the endpoint, and that approving replays it as the
original requester, not the reviewer.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.inventory import City, Item, Kit, KitTemplate, Location, Movement, StockLevel, Warehouse
from app.models.inventory.approval import InventoryActionPolicy, InventoryApprovalRequest
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


async def _turn_on(db, action_type: str) -> None:
    policy = await db.get(InventoryActionPolicy, action_type)
    if policy is None:
        policy = InventoryActionPolicy(action_type=action_type)
        db.add(policy)
    policy.requires_approval = True
    await db.commit()


async def _kit_and_warehouses(db):
    loc = Location(id=uuid.uuid4(), name=f"L{uuid.uuid4().hex[:4]}", country="AE")
    db.add(loc)
    await db.flush()
    wh_a = Warehouse(id=uuid.uuid4(), location_id=loc.id, name="A")
    wh_b = Warehouse(id=uuid.uuid4(), location_id=loc.id, name="B")
    db.add_all([wh_a, wh_b])
    await db.flush()
    tpl = KitTemplate(id=uuid.uuid4(), name="SatKit", code=f"T{uuid.uuid4().hex[:5]}")
    db.add(tpl)
    await db.flush()
    kit = Kit(
        id=uuid.uuid4(), template_id=tpl.id, label=f"SP-K-{uuid.uuid4().hex[:6]}",
        public_token=uuid.uuid4().hex * 2, current_location_id=loc.id, current_warehouse_id=wh_a.id,
    )
    db.add(kit)
    await db.commit()
    return kit, wh_a, wh_b


@pytest.mark.asyncio
async def test_kit_move_executes_immediately_while_the_policy_is_off(client, db):
    ops = await _user(db, "operations")
    kit, wh_a, wh_b = await _kit_and_warehouses(db)

    resp = await client.post(f"/inventory/kits/{kit.id}/move", headers=_headers(ops), json={
        "to_warehouse_id": str(wh_b.id), "reason": "transfer",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["reason"] == "transfer"


@pytest.mark.asyncio
async def test_kit_move_queues_for_an_operations_user_once_the_policy_is_on(client, db):
    ops = await _user(db, "operations")
    kit, wh_a, wh_b = await _kit_and_warehouses(db)
    await _turn_on(db, "kit.move")

    resp = await client.post(f"/inventory/kits/{kit.id}/move", headers=_headers(ops), json={
        "to_warehouse_id": str(wh_b.id), "reason": "transfer",
    })
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "pending_approval"
    request_id = resp.json()["approval_request_id"]

    await db.refresh(kit)
    assert kit.current_warehouse_id == wh_a.id, "nothing happens until it's approved"

    # the requester can see their own ticket...
    mine = await client.get("/inventory/approvals/mine", headers=_headers(ops))
    assert mine.status_code == 200
    [ticket] = mine.json()
    assert ticket["id"] == request_id
    assert ticket["status"] == "pending"
    assert kit.label in ticket["summary"]

    # ...an unrelated account doesn't see someone else's ticket
    other_ops = await _user(db, "operations")
    other_mine = await client.get("/inventory/approvals/mine", headers=_headers(other_ops))
    assert other_mine.json() == []


@pytest.mark.asyncio
async def test_coo_bypasses_the_gate_even_with_the_policy_on(client, db):
    coo = await _user(db, "coo")
    kit, wh_a, wh_b = await _kit_and_warehouses(db)
    await _turn_on(db, "kit.move")

    resp = await client.post(f"/inventory/kits/{kit.id}/move", headers=_headers(coo), json={
        "to_warehouse_id": str(wh_b.id), "reason": "transfer",
    })
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_approving_a_pending_kit_move_executes_it_as_the_original_requester(client, db):
    ops = await _user(db, "operations")
    coo = await _user(db, "coo")
    kit, wh_a, wh_b = await _kit_and_warehouses(db)
    await _turn_on(db, "kit.move")

    queued = await client.post(f"/inventory/kits/{kit.id}/move", headers=_headers(ops), json={
        "to_warehouse_id": str(wh_b.id), "reason": "transfer",
    })
    request_id = queued.json()["approval_request_id"]

    approved = await client.post(
        f"/inventory/approvals/{request_id}/approve", headers=_headers(coo), json={"note": "looks fine"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["reviewed_by_user_id"] == str(coo.id)
    assert approved.json()["review_note"] == "looks fine"

    await db.refresh(kit)
    assert kit.current_warehouse_id == wh_b.id

    created_by = (await db.execute(
        select(Movement.created_by).where(Movement.kit_id == kit.id).order_by(Movement.created_at.desc())
    )).scalars().first()
    assert created_by == ops.id, "the Movement is attributed to the requester, not the approving coo"


@pytest.mark.asyncio
async def test_rejecting_a_pending_request_leaves_it_undone(client, db):
    ops = await _user(db, "operations")
    coo = await _user(db, "coo")
    kit, wh_a, wh_b = await _kit_and_warehouses(db)
    await _turn_on(db, "kit.move")

    queued = await client.post(f"/inventory/kits/{kit.id}/move", headers=_headers(ops), json={
        "to_warehouse_id": str(wh_b.id), "reason": "transfer",
    })
    request_id = queued.json()["approval_request_id"]

    rejected = await client.post(
        f"/inventory/approvals/{request_id}/reject", headers=_headers(coo), json={"note": "not yet"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    await db.refresh(kit)
    assert kit.current_warehouse_id == wh_a.id


@pytest.mark.asyncio
async def test_deciding_an_already_decided_request_is_a_409(client, db):
    ops = await _user(db, "operations")
    coo = await _user(db, "coo")
    kit, wh_a, wh_b = await _kit_and_warehouses(db)
    await _turn_on(db, "kit.move")

    queued = await client.post(f"/inventory/kits/{kit.id}/move", headers=_headers(ops), json={
        "to_warehouse_id": str(wh_b.id), "reason": "transfer",
    })
    request_id = queued.json()["approval_request_id"]

    first = await client.post(f"/inventory/approvals/{request_id}/approve", headers=_headers(coo), json={})
    assert first.status_code == 200
    second = await client.post(f"/inventory/approvals/{request_id}/reject", headers=_headers(coo), json={})
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_an_operations_user_cannot_touch_the_policy_settings_or_the_queue(client, db):
    ops = await _user(db, "operations")

    assert (await client.get("/inventory/approval-policies", headers=_headers(ops))).status_code == 403
    assert (await client.put(
        "/inventory/approval-policies/kit.move", headers=_headers(ops), json={"requires_approval": True},
    )).status_code == 403
    assert (await client.get("/inventory/approvals", headers=_headers(ops))).status_code == 403


@pytest.mark.asyncio
async def test_coo_can_list_and_toggle_policies(client, db):
    coo = await _user(db, "coo")

    listed = await client.get("/inventory/approval-policies", headers=_headers(coo))
    assert listed.status_code == 200
    assert {p["action_type"] for p in listed.json()} == {
        "kit.move", "merch.issue", "merch.return", "stock.adjust",
    }
    assert all(p["requires_approval"] is False for p in listed.json())

    toggled = await client.put(
        "/inventory/approval-policies/stock.adjust", headers=_headers(coo), json={"requires_approval": True},
    )
    assert toggled.status_code == 200
    assert toggled.json()["requires_approval"] is True
    assert toggled.json()["updated_by_name"] == coo.full_name


@pytest.mark.asyncio
async def test_a_storekeepers_stock_adjustment_queues_once_the_policy_is_on(client, db):
    keeper = await _user(db, "storekeeper")
    coo = await _user(db, "coo")

    loc = Location(id=uuid.uuid4(), name=f"L{uuid.uuid4().hex[:4]}", country="AE")
    db.add(loc)
    await db.flush()
    wh = Warehouse(id=uuid.uuid4(), location_id=loc.id, name="Main")
    db.add(wh)
    await db.flush()
    item = Item(id=uuid.uuid4(), name=f"MPU {uuid.uuid4().hex[:4]}", category="board")
    db.add(item)
    await db.flush()
    level = StockLevel(id=uuid.uuid4(), item_id=item.id, warehouse_id=wh.id, qty=3)
    db.add(level)
    await db.commit()
    await _turn_on(db, "stock.adjust")

    resp = await client.post("/inventory/stock/adjust", headers=_headers(keeper), json={
        "item_id": str(item.id), "warehouse_id": str(wh.id), "new_qty": 9, "reason": "recount",
    })
    assert resp.status_code == 202, resp.text
    request_id = resp.json()["approval_request_id"]

    await db.refresh(level)
    assert level.qty == 3, "nothing changes until it's approved"

    approved = await client.post(f"/inventory/approvals/{request_id}/approve", headers=_headers(coo), json={})
    assert approved.status_code == 200

    await db.refresh(level)
    assert level.qty == 9


@pytest.mark.asyncio
async def test_a_storekeepers_bulk_stocktake_queues_as_one_ticket_not_one_per_line(client, db):
    keeper = await _user(db, "storekeeper")

    loc = Location(id=uuid.uuid4(), name=f"L{uuid.uuid4().hex[:4]}", country="AE")
    db.add(loc)
    await db.flush()
    wh = Warehouse(id=uuid.uuid4(), location_id=loc.id, name="Main")
    db.add(wh)
    await db.flush()
    items = [Item(id=uuid.uuid4(), name=f"Item {i}-{uuid.uuid4().hex[:4]}", category="board") for i in range(2)]
    db.add_all(items)
    await db.flush()
    db.add_all([StockLevel(id=uuid.uuid4(), item_id=i.id, warehouse_id=wh.id, qty=1) for i in items])
    await db.commit()
    await _turn_on(db, "stock.adjust")

    resp = await client.post("/inventory/stock/adjust-bulk", headers=_headers(keeper), json={
        "reason": "Monthly stocktake",
        "levels": [
            {"item_id": str(items[0].id), "warehouse_id": str(wh.id), "new_qty": 5},
            {"item_id": str(items[1].id), "warehouse_id": str(wh.id), "new_qty": 6},
        ],
    })
    assert resp.status_code == 202, resp.text

    pending = (await db.execute(
        InventoryApprovalRequest.__table__.select().where(InventoryApprovalRequest.action_type == "stock.adjust")
    )).all()
    assert len(pending) == 1, "one ticket for the whole stocktake, not one per line"
