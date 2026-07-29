"""Service-layer tests for inventory (I1-2). Redis-free, HTTP-free."""

import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.inventory import (
    Item,
    Kit,
    KitItem,
    KitTemplate,
    KitTemplateItem,
    Location,
    Movement,
    StockLevel,
)
from app.models.user import User
from app.services.inventory import (
    adjust_stock,
    confirm,
    is_complete,
    kit_shortages,
    move,
    overdue,
    shortages_for_kits,
)


# ── factories ───────────────────────────────────────────────────────────────

async def _loc(db, name="Dubai") -> Location:
    loc = Location(id=uuid.uuid4(), name=name, country="AE")
    db.add(loc)
    await db.flush()
    return loc


async def _item(db, name=None, **kw) -> Item:
    item = Item(id=uuid.uuid4(), name=name or f"Item {uuid.uuid4().hex[:8]}", **kw)
    db.add(item)
    await db.flush()
    return item


async def _user(db) -> User:
    u = User(
        id=uuid.uuid4(), full_name="Ops", email=f"s-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(u)
    await db.flush()
    return u


async def _kit_with_template(db, loc, *, required: dict[Item, int]) -> tuple[Kit, KitTemplate]:
    tpl = KitTemplate(id=uuid.uuid4(), name="SatKit", code=f"T{uuid.uuid4().hex[:6]}")
    db.add(tpl)
    await db.flush()
    for item, qty in required.items():
        db.add(KitTemplateItem(id=uuid.uuid4(), template_id=tpl.id, item_id=item.id, required_qty=qty))
    kit = Kit(
        id=uuid.uuid4(), template_id=tpl.id,
        label=f"SP-SATKIT-{uuid.uuid4().hex[:4]}", public_token=uuid.uuid4().hex * 2,
        current_location_id=loc.id,
    )
    db.add(kit)
    await db.flush()
    return kit, tpl


async def _stock(db, item, loc, qty) -> StockLevel:
    lvl = StockLevel(id=uuid.uuid4(), item_id=item.id, location_id=loc.id, qty=qty)
    db.add(lvl)
    await db.flush()
    return lvl


# ── completeness ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_complete_kit_has_no_shortages(db):
    loc = await _loc(db)
    board = await _item(db, name="EPS Board")
    kit, _ = await _kit_with_template(db, loc, required={board: 1})
    db.add(KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=board.id, qty=1))
    await db.flush()

    assert await kit_shortages(db, kit) == []
    assert await is_complete(db, kit) is True


@pytest.mark.asyncio
async def test_a_missing_row_counts_as_zero_not_as_complete(db):
    """The dangerous case: the component was never recorded at all. A missing
    row and a row saying 0 mean the same thing physically."""
    loc = await _loc(db)
    board = await _item(db, name="EPS Board")
    kit, _ = await _kit_with_template(db, loc, required={board: 1})
    # deliberately no KitItem row

    shortages = await kit_shortages(db, kit)
    assert len(shortages) == 1
    assert shortages[0]["actual"] == 0
    assert shortages[0]["short_by"] == 1
    assert await is_complete(db, kit) is False


@pytest.mark.asyncio
async def test_consumables_are_never_a_shortage(db):
    """20 screws per kit means a post-workshop count is always short a few.
    If that counts as incomplete, the shortage list is noise forever — and
    the missing ADCS board hides in it."""
    loc = await _loc(db)
    screw = await _item(db, name="M3 Screw", is_consumable=True)
    board = await _item(db, name="ADCS Board")
    kit, _ = await _kit_with_template(db, loc, required={screw: 20, board: 1})
    db.add_all([
        KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=screw.id, qty=14),  # 6 short
        KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=board.id, qty=1),
    ])
    await db.flush()

    assert await kit_shortages(db, kit) == []
    assert await is_complete(db, kit) is True


@pytest.mark.asyncio
async def test_shortages_are_worst_first(db):
    loc = await _loc(db)
    a = await _item(db, name="Aaa Board")
    b = await _item(db, name="Bbb Sensor")
    kit, _ = await _kit_with_template(db, loc, required={a: 2, b: 10})
    await db.flush()

    shortages = await kit_shortages(db, kit)
    assert [s["item_name"] for s in shortages] == ["Bbb Sensor", "Aaa Board"]


@pytest.mark.asyncio
async def test_bulk_shortage_counts_for_a_list_view(db):
    loc = await _loc(db)
    board = await _item(db, name="EPS Board")
    good, _ = await _kit_with_template(db, loc, required={board: 1})
    db.add(KitItem(id=uuid.uuid4(), kit_id=good.id, item_id=board.id, qty=1))
    bad, _ = await _kit_with_template(db, loc, required={board: 1})
    await db.flush()

    counts = await shortages_for_kits(db, [good.id, bad.id])
    assert counts[good.id] == 0
    assert counts[bad.id] == 1


@pytest.mark.asyncio
async def test_bulk_shortage_of_nothing_is_empty(db):
    assert await shortages_for_kits(db, []) == {}


# ── moving a kit ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_issuing_a_kit_sets_the_holder_and_keeps_the_location(db):
    """A kit at a workshop still belongs to its warehouse — that is what keeps
    "what is in Dubai" answerable while it is out."""
    dubai = await _loc(db)
    actor = await _user(db)
    holder = await _user(db)
    kit, _ = await _kit_with_template(db, dubai, required={})

    await move(db, actor_user_id=actor.id, reason="issue", kit_id=kit.id,
               from_location_id=dubai.id, to_user_id=holder.id)

    assert kit.current_holder_user_id == holder.id
    assert kit.current_location_id == dubai.id


@pytest.mark.asyncio
async def test_returning_a_kit_clears_the_holder(db):
    dubai = await _loc(db)
    abudhabi = await _loc(db, name="Abu Dhabi")
    actor = await _user(db)
    holder = await _user(db)
    kit, _ = await _kit_with_template(db, dubai, required={})

    await move(db, actor_user_id=actor.id, reason="issue", kit_id=kit.id, to_user_id=holder.id)
    await move(db, actor_user_id=actor.id, reason="return", kit_id=kit.id,
               from_user_id=holder.id, to_location_id=abudhabi.id)

    assert kit.current_holder_user_id is None, "nobody holds a kit sitting on a shelf"
    assert kit.current_location_id == abudhabi.id


@pytest.mark.asyncio
async def test_a_kit_may_not_carry_a_quantity(db):
    dubai = await _loc(db)
    actor = await _user(db)
    kit, _ = await _kit_with_template(db, dubai, required={})
    with pytest.raises(HTTPException) as exc:
        await move(db, actor_user_id=actor.id, reason="issue", kit_id=kit.id,
                   qty=3, to_location_id=dubai.id)
    assert exc.value.status_code == 400


# ── moving stock ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_transfer_moves_quantity_between_locations(db):
    dubai = await _loc(db)
    cairo = await _loc(db, name="Cairo")
    actor = await _user(db)
    mpu = await _item(db)
    src = await _stock(db, mpu, dubai, 10)

    await move(db, actor_user_id=actor.id, reason="transfer", item_id=mpu.id, qty=4,
               from_location_id=dubai.id, to_location_id=cairo.id)

    dest = (await db.execute(select(StockLevel).where(
        StockLevel.item_id == mpu.id, StockLevel.location_id == cairo.id
    ))).scalars().first()
    assert src.qty == 6
    assert dest is not None and dest.qty == 4


@pytest.mark.asyncio
async def test_stock_cannot_go_negative(db):
    dubai = await _loc(db)
    cairo = await _loc(db, name="Cairo")
    actor = await _user(db)
    mpu = await _item(db)
    src = await _stock(db, mpu, dubai, 3)

    with pytest.raises(HTTPException) as exc:
        await move(db, actor_user_id=actor.id, reason="transfer", item_id=mpu.id, qty=5,
                   from_location_id=dubai.id, to_location_id=cairo.id)
    assert exc.value.status_code == 409
    assert src.qty == 3, "the failed move must not have taken anything"


@pytest.mark.asyncio
async def test_receiving_goods_needs_no_source(db):
    dubai = await _loc(db)
    actor = await _user(db)
    mpu = await _item(db)

    await move(db, actor_user_id=actor.id, reason="receive", item_id=mpu.id, qty=24,
               to_location_id=dubai.id)

    level = (await db.execute(select(StockLevel).where(
        StockLevel.item_id == mpu.id, StockLevel.location_id == dubai.id
    ))).scalars().first()
    assert level.qty == 24


@pytest.mark.asyncio
async def test_moving_an_item_needs_a_positive_quantity(db):
    dubai = await _loc(db)
    actor = await _user(db)
    mpu = await _item(db)
    for bad in (None, 0, -2):
        with pytest.raises(HTTPException) as exc:
            await move(db, actor_user_id=actor.id, reason="receive", item_id=mpu.id,
                       qty=bad, to_location_id=dubai.id)
        assert exc.value.status_code == 400


# ── movement validation ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_movement_is_of_one_thing(db):
    dubai = await _loc(db)
    actor = await _user(db)
    kit, _ = await _kit_with_template(db, dubai, required={})
    mpu = await _item(db)

    with pytest.raises(HTTPException):
        await move(db, actor_user_id=actor.id, reason="issue", kit_id=kit.id,
                   item_id=mpu.id, qty=1, to_location_id=dubai.id)
    with pytest.raises(HTTPException):
        await move(db, actor_user_id=actor.id, reason="issue", to_location_id=dubai.id)


@pytest.mark.asyncio
async def test_unknown_reason_is_rejected(db):
    dubai = await _loc(db)
    actor = await _user(db)
    kit, _ = await _kit_with_template(db, dubai, required={})
    with pytest.raises(HTTPException) as exc:
        await move(db, actor_user_id=actor.id, reason="teleport", kit_id=kit.id,
                   to_location_id=dubai.id)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_a_destination_is_required_except_for_writeoff_and_adjust(db):
    dubai = await _loc(db)
    actor = await _user(db)
    kit, _ = await _kit_with_template(db, dubai, required={})

    with pytest.raises(HTTPException):
        await move(db, actor_user_id=actor.id, reason="issue", kit_id=kit.id)

    await move(db, actor_user_id=actor.id, reason="writeoff", kit_id=kit.id)  # allowed


@pytest.mark.asyncio
async def test_something_cannot_go_to_a_place_and_a_person_at_once(db):
    dubai = await _loc(db)
    actor = await _user(db)
    holder = await _user(db)
    kit, _ = await _kit_with_template(db, dubai, required={})
    with pytest.raises(HTTPException):
        await move(db, actor_user_id=actor.id, reason="issue", kit_id=kit.id,
                   to_location_id=dubai.id, to_user_id=holder.id)


@pytest.mark.asyncio
async def test_a_return_deadline_only_applies_to_a_person(db):
    """A due-back date on a warehouse transfer would sit on the overdue list
    forever, because a warehouse never hands anything back."""
    dubai = await _loc(db)
    cairo = await _loc(db, name="Cairo")
    actor = await _user(db)
    kit, _ = await _kit_with_template(db, dubai, required={})
    with pytest.raises(HTTPException):
        await move(db, actor_user_id=actor.id, reason="transfer", kit_id=kit.id,
                   to_location_id=cairo.id, due_back_on=date.today())


# ── confirmation ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirmation_is_recorded_and_idempotent(db):
    dubai = await _loc(db)
    actor = await _user(db)
    other = await _user(db)
    kit, _ = await _kit_with_template(db, dubai, required={})
    mv = await move(db, actor_user_id=actor.id, reason="issue", kit_id=kit.id, to_user_id=other.id)
    assert mv.confirmed_at is None, "a movement is real before anyone confirms it"

    await confirm(db, mv, actor_user_id=other.id)
    first = mv.confirmed_at
    assert first is not None and mv.confirmed_by == other.id

    await confirm(db, mv, actor_user_id=actor.id)
    assert mv.confirmed_at == first, "the first confirmation is the true record"
    assert mv.confirmed_by == other.id


# ── overdue ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_overdue_lists_only_what_is_still_out(db):
    dubai = await _loc(db)
    actor = await _user(db)
    holder = await _user(db)
    vest = await _item(db, name="Vest L", returnable_default=True)
    await _stock(db, vest, dubai, 5)
    yesterday = date.today() - timedelta(days=1)

    kept, _ = await _kit_with_template(db, dubai, required={})
    given_back, _ = await _kit_with_template(db, dubai, required={})

    await move(db, actor_user_id=actor.id, reason="issue", kit_id=kept.id,
               to_user_id=holder.id, due_back_on=yesterday)
    await move(db, actor_user_id=actor.id, reason="issue", kit_id=given_back.id,
               to_user_id=holder.id, due_back_on=yesterday)
    await move(db, actor_user_id=actor.id, reason="return", kit_id=given_back.id,
               from_user_id=holder.id, to_location_id=dubai.id)

    still_out = await overdue(db)
    assert [m.kit_id for m in still_out] == [kept.id]


@pytest.mark.asyncio
async def test_nothing_without_a_deadline_is_ever_overdue(db):
    """A kit that lives with an instructor indefinitely, or a T-shirt that was
    a gift, must never appear — otherwise the list becomes noise."""
    dubai = await _loc(db)
    actor = await _user(db)
    holder = await _user(db)
    kit, _ = await _kit_with_template(db, dubai, required={})
    await move(db, actor_user_id=actor.id, reason="issue", kit_id=kit.id, to_user_id=holder.id)

    assert await overdue(db) == []


# ── stock adjustment ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_adjustment_sets_the_counted_total_and_records_the_delta(db):
    dubai = await _loc(db)
    actor = await _user(db)
    mpu = await _item(db)
    level = await _stock(db, mpu, dubai, 40)

    mv = await adjust_stock(db, actor_user_id=actor.id, item_id=mpu.id,
                            location_id=dubai.id, new_qty=38, reason="stocktake")

    assert level.qty == 38
    assert mv.qty == 2
    assert "-2" in mv.note and "40 → 38" in mv.note and "stocktake" in mv.note


@pytest.mark.asyncio
async def test_adjustment_can_create_a_level_that_did_not_exist(db):
    dubai = await _loc(db)
    actor = await _user(db)
    mpu = await _item(db)

    await adjust_stock(db, actor_user_id=actor.id, item_id=mpu.id,
                       location_id=dubai.id, new_qty=7, reason="found a box")

    level = (await db.execute(select(StockLevel).where(
        StockLevel.item_id == mpu.id, StockLevel.location_id == dubai.id
    ))).scalars().first()
    assert level.qty == 7


@pytest.mark.asyncio
async def test_adjustment_requires_a_reason(db):
    dubai = await _loc(db)
    actor = await _user(db)
    mpu = await _item(db)
    for bad in ("", "   "):
        with pytest.raises(HTTPException) as exc:
            await adjust_stock(db, actor_user_id=actor.id, item_id=mpu.id,
                               location_id=dubai.id, new_qty=1, reason=bad)
        assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_adjustment_refuses_negative_and_no_op(db):
    dubai = await _loc(db)
    actor = await _user(db)
    mpu = await _item(db)
    await _stock(db, mpu, dubai, 5)

    with pytest.raises(HTTPException) as exc:
        await adjust_stock(db, actor_user_id=actor.id, item_id=mpu.id,
                           location_id=dubai.id, new_qty=-1, reason="x")
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await adjust_stock(db, actor_user_id=actor.id, item_id=mpu.id,
                           location_id=dubai.id, new_qty=5, reason="x")
    assert exc.value.status_code == 409


# ── a kit as a container: refill and cannibalise ────────────────────────────

@pytest.mark.asyncio
async def test_refilling_moves_stock_out_of_the_warehouse_and_into_the_kit(db):
    """The storekeeper's whole job. One call updates both sides."""
    dubai = await _loc(db)
    actor = await _user(db)
    mpu = await _item(db, name="MPU-9250")
    kit, _ = await _kit_with_template(db, dubai, required={mpu: 1})
    shelf = await _stock(db, mpu, dubai, 10)

    await move(db, actor_user_id=actor.id, reason="refill", item_id=mpu.id, qty=1,
               from_location_id=dubai.id, to_kit_id=kit.id)

    contents = (await db.execute(select(KitItem).where(
        KitItem.kit_id == kit.id, KitItem.item_id == mpu.id
    ))).scalars().first()
    assert shelf.qty == 9
    assert contents is not None and contents.qty == 1
    assert await is_complete(db, kit) is True


@pytest.mark.asyncio
async def test_cannibalising_takes_parts_back_out_of_a_kit(db):
    """Stripping one kit to make another complete before a workshop — it
    happens, and the ledger should be able to say so."""
    dubai = await _loc(db)
    actor = await _user(db)
    board = await _item(db, name="ADCS Board")
    donor, _ = await _kit_with_template(db, dubai, required={board: 1})
    db.add(KitItem(id=uuid.uuid4(), kit_id=donor.id, item_id=board.id, qty=1))
    await db.flush()
    receiver, _ = await _kit_with_template(db, dubai, required={board: 1})

    await move(db, actor_user_id=actor.id, reason="transfer", item_id=board.id, qty=1,
               from_kit_id=donor.id, to_kit_id=receiver.id)

    assert await is_complete(db, receiver) is True
    assert await is_complete(db, donor) is False


@pytest.mark.asyncio
async def test_a_kit_cannot_give_what_it_does_not_have(db):
    dubai = await _loc(db)
    actor = await _user(db)
    board = await _item(db)
    donor, _ = await _kit_with_template(db, dubai, required={board: 1})

    with pytest.raises(HTTPException) as exc:
        await move(db, actor_user_id=actor.id, reason="transfer", item_id=board.id, qty=1,
                   from_kit_id=donor.id, to_location_id=dubai.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_a_kit_cannot_go_inside_a_kit(db):
    dubai = await _loc(db)
    actor = await _user(db)
    outer, _ = await _kit_with_template(db, dubai, required={})
    inner, _ = await _kit_with_template(db, dubai, required={})

    with pytest.raises(HTTPException) as exc:
        await move(db, actor_user_id=actor.id, reason="transfer", kit_id=inner.id,
                   to_kit_id=outer.id)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_a_movement_has_one_destination_of_three_kinds(db):
    dubai = await _loc(db)
    actor = await _user(db)
    holder = await _user(db)
    mpu = await _item(db)
    kit, _ = await _kit_with_template(db, dubai, required={})

    with pytest.raises(HTTPException) as exc:
        await move(db, actor_user_id=actor.id, reason="refill", item_id=mpu.id, qty=1,
                   to_kit_id=kit.id, to_user_id=holder.id)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_every_movement_lands_in_the_one_ledger(db):
    """Transfers, receipts and corrections all end up queryable together —
    the reason the legacy system's four separate tables became one."""
    dubai = await _loc(db)
    actor = await _user(db)
    mpu = await _item(db)

    await move(db, actor_user_id=actor.id, reason="receive", item_id=mpu.id, qty=10,
               to_location_id=dubai.id)
    await adjust_stock(db, actor_user_id=actor.id, item_id=mpu.id,
                       location_id=dubai.id, new_qty=9, reason="one was broken")

    rows = (await db.execute(select(Movement).where(Movement.item_id == mpu.id))).scalars().all()
    assert sorted(m.reason for m in rows) == ["adjust", "receive"]
