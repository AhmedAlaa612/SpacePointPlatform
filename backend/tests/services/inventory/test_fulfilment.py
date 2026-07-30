"""The storekeeper fulfilment loop (I3-1).

What these pin is mostly that the queue is *derived* — there is no task
table, so "the task exists" and "the task is closed" are both consequences of
the kit's contents rather than rows anyone maintains. The single stored fact
is the storekeeper's "I looked and there were none".
"""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.inventory import Item, Kit, KitItem, KitTemplate, Location, StockLevel
from app.models.inventory.kit_template import KitTemplateItem
from app.models.user import User
from app.services.inventory import (
    fulfil_kit,
    fulfilment_queue,
    set_awaiting_parts,
)


async def _user(db) -> User:
    u = User(
        id=uuid.uuid4(), full_name=f"P{uuid.uuid4().hex[:4]}",
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["storekeeper"], status="active",
    )
    db.add(u)
    await db.flush()
    return u


async def _loc(db, name="Dubai") -> Location:
    loc = Location(id=uuid.uuid4(), name=name, country="AE")
    db.add(loc)
    await db.flush()
    return loc


async def _item(db, name="MPU", consumable=False) -> Item:
    item = Item(
        id=uuid.uuid4(), name=f"{name} {uuid.uuid4().hex[:4]}", category="board",
        is_consumable=consumable, returnable_default=False,
    )
    db.add(item)
    await db.flush()
    return item


async def _kit_needing(db, loc, needs: list[tuple[Item, int, int]]) -> Kit:
    """`needs` is (item, required, actually_present)."""
    tpl = KitTemplate(id=uuid.uuid4(), name="SatKit", code=f"T{uuid.uuid4().hex[:5]}")
    db.add(tpl)
    await db.flush()
    for item, required, _present in needs:
        db.add(KitTemplateItem(
            id=uuid.uuid4(), template_id=tpl.id, item_id=item.id, required_qty=required
        ))
    kit = Kit(
        id=uuid.uuid4(), template_id=tpl.id, label=f"SP-K-{uuid.uuid4().hex[:6]}",
        public_token=uuid.uuid4().hex * 2, current_location_id=loc.id,
    )
    db.add(kit)
    await db.flush()
    for item, _required, present in needs:
        if present:
            db.add(KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=item.id, qty=present))
    await db.flush()
    return kit


async def _stock(db, item, loc, qty) -> None:
    db.add(StockLevel(id=uuid.uuid4(), item_id=item.id, location_id=loc.id, qty=qty))
    await db.flush()


# ── the queue is derived ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_short_kit_appears_with_what_is_on_its_own_shelf(db):
    loc = await _loc(db)
    mpu = await _item(db)
    kit = await _kit_needing(db, loc, [(mpu, 5, 3)])
    await _stock(db, mpu, loc, 10)

    [row] = [r for r in await fulfilment_queue(db) if r["kit_id"] == kit.id]
    assert row["label"] == kit.label
    [line] = row["shortages"]
    assert (line["required"], line["actual"], line["short_by"]) == (5, 3, 2)
    assert line["available"] == 10
    assert row["fixable_now"] == 1


@pytest.mark.asyncio
async def test_stock_at_another_warehouse_does_not_count_as_available(db):
    """The storekeeper is standing at one shelf. Counting a part 400km away as
    available is how the list stops being trusted."""
    here, elsewhere = await _loc(db, "Dubai"), await _loc(db, "Sharjah")
    mpu = await _item(db)
    kit = await _kit_needing(db, here, [(mpu, 5, 3)])
    await _stock(db, mpu, elsewhere, 50)

    [row] = [r for r in await fulfilment_queue(db) if r["kit_id"] == kit.id]
    assert row["shortages"][0]["available"] == 0
    assert row["fixable_now"] == 0


@pytest.mark.asyncio
async def test_a_complete_kit_is_not_in_the_queue_at_all(db):
    loc = await _loc(db)
    mpu = await _item(db)
    kit = await _kit_needing(db, loc, [(mpu, 5, 5)])

    assert [r for r in await fulfilment_queue(db) if r["kit_id"] == kit.id] == []


@pytest.mark.asyncio
async def test_consumables_never_put_a_kit_in_the_queue(db):
    """D10. Twenty screws per kit means a post-workshop count is always short a
    few; counting them makes the queue permanently non-empty and the missing
    ADCS board hides inside it."""
    loc = await _loc(db)
    screw = await _item(db, name="M3 screw", consumable=True)
    kit = await _kit_needing(db, loc, [(screw, 20, 4)])

    assert [r for r in await fulfilment_queue(db) if r["kit_id"] == kit.id] == []


@pytest.mark.asyncio
async def test_retired_and_lost_kits_are_left_out(db):
    loc = await _loc(db)
    mpu = await _item(db)
    kit = await _kit_needing(db, loc, [(mpu, 5, 0)])
    kit.status = "retired"
    await db.flush()

    assert [r for r in await fulfilment_queue(db) if r["kit_id"] == kit.id] == []


@pytest.mark.asyncio
async def test_the_queue_can_be_filtered_to_one_warehouse(db):
    dubai, sharjah = await _loc(db, "Dubai"), await _loc(db, "Sharjah")
    mpu = await _item(db)
    mine = await _kit_needing(db, dubai, [(mpu, 5, 1)])
    theirs = await _kit_needing(db, sharjah, [(mpu, 5, 1)])

    ids = {r["kit_id"] for r in await fulfilment_queue(db, location_id=dubai.id)}
    assert mine.id in ids and theirs.id not in ids


# ── fulfilling ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fulfilling_moves_stock_into_the_kit_and_closes_the_task(db):
    """No task is closed as such — the shortage stops existing, so the kit
    drops off the queue on its own."""
    keeper = await _user(db)
    loc = await _loc(db)
    mpu = await _item(db)
    kit = await _kit_needing(db, loc, [(mpu, 5, 3)])
    await _stock(db, mpu, loc, 10)

    [movement] = await fulfil_kit(
        db, kit=kit, lines=[(mpu.id, 2)], actor_user_id=keeper.id
    )
    assert movement.reason == "refill"
    assert movement.from_location_id == loc.id     # the kit's own shelf, derived
    assert movement.to_kit_id == kit.id

    level = (await db.execute(select(StockLevel).where(
        StockLevel.item_id == mpu.id, StockLevel.location_id == loc.id
    ))).scalars().first()
    assert level.qty == 8

    contents = (await db.execute(select(KitItem).where(
        KitItem.kit_id == kit.id, KitItem.item_id == mpu.id
    ))).scalars().first()
    assert contents.qty == 5

    assert [r for r in await fulfilment_queue(db) if r["kit_id"] == kit.id] == []


@pytest.mark.asyncio
async def test_fulfilling_more_than_the_shelf_holds_is_refused(db):
    """`move()` refuses to drive stock negative and this does not weaken it —
    the storekeeper's numbers are the ones everyone else relies on."""
    keeper = await _user(db)
    loc = await _loc(db)
    mpu = await _item(db)
    kit = await _kit_needing(db, loc, [(mpu, 5, 0)])
    await _stock(db, mpu, loc, 2)

    with pytest.raises(HTTPException) as exc:
        await fulfil_kit(db, kit=kit, lines=[(mpu.id, 5)], actor_user_id=keeper.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_a_partial_fulfilment_leaves_the_kit_in_the_queue(db):
    keeper = await _user(db)
    loc = await _loc(db)
    mpu = await _item(db)
    kit = await _kit_needing(db, loc, [(mpu, 5, 0)])
    await _stock(db, mpu, loc, 10)

    await fulfil_kit(db, kit=kit, lines=[(mpu.id, 3)], actor_user_id=keeper.id)

    [row] = [r for r in await fulfilment_queue(db) if r["kit_id"] == kit.id]
    assert row["shortages"][0]["short_by"] == 2


@pytest.mark.asyncio
async def test_parts_can_be_pulled_from_another_warehouse_when_asked(db):
    keeper = await _user(db)
    here, elsewhere = await _loc(db, "Dubai"), await _loc(db, "Sharjah")
    mpu = await _item(db)
    kit = await _kit_needing(db, here, [(mpu, 5, 4)])
    await _stock(db, mpu, elsewhere, 6)

    [movement] = await fulfil_kit(
        db, kit=kit, lines=[(mpu.id, 1)],
        actor_user_id=keeper.id, from_location_id=elsewhere.id,
    )
    assert movement.from_location_id == elsewhere.id


# ── "I looked and there were none" ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_flagging_awaiting_parts_records_when_and_why(db):
    loc = await _loc(db)
    mpu = await _item(db)
    kit = await _kit_needing(db, loc, [(mpu, 5, 1)])

    await set_awaiting_parts(db, kit=kit, awaiting=True, note="none left anywhere")
    assert kit.awaiting_parts_since is not None
    assert kit.awaiting_parts_note == "none left anywhere"

    [row] = [r for r in await fulfilment_queue(db) if r["kit_id"] == kit.id]
    assert row["awaiting_parts_since"] is not None


@pytest.mark.asyncio
async def test_flagging_twice_keeps_the_original_timestamp(db):
    """How long a kit has been waiting is the number worth having. Re-flagging
    would reset the clock on exactly the kits that have waited longest."""
    loc = await _loc(db)
    mpu = await _item(db)
    kit = await _kit_needing(db, loc, [(mpu, 5, 1)])

    await set_awaiting_parts(db, kit=kit, awaiting=True, note="first")
    first = kit.awaiting_parts_since
    await set_awaiting_parts(db, kit=kit, awaiting=True, note="chased again")

    assert kit.awaiting_parts_since == first
    assert kit.awaiting_parts_note == "chased again"


@pytest.mark.asyncio
async def test_a_kit_that_is_not_short_cannot_be_flagged(db):
    """The flag means "still waiting for something". Letting it sit on a
    complete kit is how a list stops being trustworthy."""
    loc = await _loc(db)
    mpu = await _item(db)
    kit = await _kit_needing(db, loc, [(mpu, 5, 5)])

    with pytest.raises(HTTPException) as exc:
        await set_awaiting_parts(db, kit=kit, awaiting=True)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_fulfilling_a_flagged_kit_clears_the_flag(db):
    """The parts arrived, so it is no longer waiting — and nobody should have
    to remember to untick it."""
    keeper = await _user(db)
    loc = await _loc(db)
    mpu = await _item(db)
    kit = await _kit_needing(db, loc, [(mpu, 5, 3)])
    await set_awaiting_parts(db, kit=kit, awaiting=True, note="shelf empty")
    await _stock(db, mpu, loc, 5)

    await fulfil_kit(db, kit=kit, lines=[(mpu.id, 2)], actor_user_id=keeper.id)

    assert kit.awaiting_parts_since is None
    assert kit.awaiting_parts_note is None


@pytest.mark.asyncio
async def test_a_partial_fulfilment_does_not_clear_the_flag(db):
    """Still short, so still waiting."""
    keeper = await _user(db)
    loc = await _loc(db)
    mpu = await _item(db)
    kit = await _kit_needing(db, loc, [(mpu, 5, 0)])
    await set_awaiting_parts(db, kit=kit, awaiting=True, note="shelf empty")
    await _stock(db, mpu, loc, 2)

    await fulfil_kit(db, kit=kit, lines=[(mpu.id, 2)], actor_user_id=keeper.id)

    assert kit.awaiting_parts_since is not None
