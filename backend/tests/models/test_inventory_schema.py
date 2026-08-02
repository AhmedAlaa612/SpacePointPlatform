"""Functional schema tests for the inventory domain (I1-1).

These insert real rows rather than reviewing DDL, deliberately. The R1-2
lesson from this codebase's history: two VARCHAR widths in the spec text
didn't fit their own listed enum values, and DDL review missed it — only a
functional insert caught it.

Redis-free, HTTP-free. Just the schema.
"""

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.models.inventory import (
    Item,
    Kit,
    KitItem,
    KitTemplate,
    KitTemplateItem,
    Location,
    Movement,
    StockLevel,
    Warehouse,
)
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User


# ── factories ───────────────────────────────────────────────────────────────

async def _location(db, name="Dubai", country="AE") -> Location:
    loc = Location(id=uuid.uuid4(), name=name, country=country)
    db.add(loc)
    await db.flush()
    return loc


async def _item(db, name=None, **kw) -> Item:
    item = Item(id=uuid.uuid4(), name=name or f"Item {uuid.uuid4().hex[:8]}", **kw)
    db.add(item)
    await db.flush()
    return item


async def _template(db, code=None) -> KitTemplate:
    tpl = KitTemplate(id=uuid.uuid4(), name="SatKit v1", code=code or f"T{uuid.uuid4().hex[:6]}")
    db.add(tpl)
    await db.flush()
    return tpl


async def _user(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Ops Person",
        email=f"inv-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        roles=["operations"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _warehouse(db, location=None, name=None) -> Warehouse:
    location = location or await _location(db)
    wh = Warehouse(id=uuid.uuid4(), location_id=location.id, name=name or f"{location.name} Main")
    db.add(wh)
    await db.flush()
    return wh


async def _kit(db, *, template=None, location=None, warehouse=None, label=None, **kw) -> Kit:
    template = template or await _template(db)
    location = location or await _location(db)
    warehouse = warehouse or await _warehouse(db, location)
    kit = Kit(
        id=uuid.uuid4(),
        template_id=template.id,
        label=label or f"SP-SATKIT-{uuid.uuid4().hex[:4]}",
        public_token=uuid.uuid4().hex * 2,  # 64 chars
        current_location_id=location.id,
        current_warehouse_id=warehouse.id,
        **kw,
    )
    db.add(kit)
    await db.flush()
    return kit


async def _session(db) -> Session:
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Cohort", status="planned")
    db.add(cohort)
    await db.flush()
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today())
    db.add(session)
    await db.flush()
    return session


# ── every table takes a real row ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_kit_with_contents_and_template(db):
    """The whole serialised path in one go: template -> BOM -> kit -> contents."""
    tpl = await _template(db, code="SATKIT")
    board = await _item(db, name="EPS Board", category="board")
    screw = await _item(db, name="M3 Screw", category="mechanical")

    db.add_all([
        KitTemplateItem(id=uuid.uuid4(), template_id=tpl.id, item_id=board.id, required_qty=1),
        KitTemplateItem(id=uuid.uuid4(), template_id=tpl.id, item_id=screw.id, required_qty=20),
    ])
    await db.flush()

    kit = await _kit(db, template=tpl, label="SP-SATKIT-0001")
    db.add_all([
        KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=board.id, qty=1),
        KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=screw.id, qty=17),
    ])
    await db.flush()

    contents = (await db.execute(select(KitItem).where(KitItem.kit_id == kit.id))).scalars().all()
    assert {c.qty for c in contents} == {1, 17}
    assert kit.status == "working"          # server default
    assert kit.current_holder_user_id is None  # at its location, not out


@pytest.mark.asyncio
async def test_stock_level_per_item_per_warehouse(db):
    item = await _item(db)
    dubai = await _location(db, name="Dubai")
    egypt = await _location(db, name="Cairo", country="EG")
    dubai_wh = await _warehouse(db, dubai)
    egypt_wh = await _warehouse(db, egypt)
    db.add_all([
        StockLevel(id=uuid.uuid4(), item_id=item.id, warehouse_id=dubai_wh.id, qty=40),
        StockLevel(id=uuid.uuid4(), item_id=item.id, warehouse_id=egypt_wh.id, qty=6),
    ])
    await db.flush()

    rows = (await db.execute(select(StockLevel).where(StockLevel.item_id == item.id))).scalars().all()
    assert sorted(r.qty for r in rows) == [6, 40]


# ── the one CHECK constraint ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_movement_accepts_a_kit_alone(db):
    kit = await _kit(db)
    actor = await _user(db)
    db.add(Movement(id=uuid.uuid4(), kit_id=kit.id, reason="issue", created_by=actor.id))
    await db.flush()


@pytest.mark.asyncio
async def test_movement_accepts_an_item_with_a_quantity(db):
    item = await _item(db)
    actor = await _user(db)
    db.add(Movement(id=uuid.uuid4(), item_id=item.id, qty=5, reason="refill", created_by=actor.id))
    await db.flush()


@pytest.mark.asyncio
async def test_movement_rejects_both_a_kit_and_an_item(db):
    kit = await _kit(db)
    item = await _item(db)
    actor = await _user(db)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(Movement(
                id=uuid.uuid4(), kit_id=kit.id, item_id=item.id, qty=1,
                reason="issue", created_by=actor.id,
            ))
            await db.flush()


@pytest.mark.asyncio
async def test_movement_rejects_neither(db):
    """A movement of nothing is meaningless — the ledger must not hold one."""
    actor = await _user(db)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(Movement(id=uuid.uuid4(), reason="adjust", created_by=actor.id))
            await db.flush()


# ── uniqueness ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kit_label_is_unique(db):
    await _kit(db, label="SP-SATKIT-0042")
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await _kit(db, label="SP-SATKIT-0042")


@pytest.mark.asyncio
async def test_a_kit_cannot_hold_the_same_item_twice(db):
    kit = await _kit(db)
    item = await _item(db)
    db.add(KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=item.id, qty=1))
    await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=item.id, qty=3))
            await db.flush()


@pytest.mark.asyncio
async def test_stock_is_one_row_per_item_and_warehouse(db):
    item = await _item(db)
    loc = await _location(db)
    wh = await _warehouse(db, loc)
    db.add(StockLevel(id=uuid.uuid4(), item_id=item.id, warehouse_id=wh.id, qty=1))
    await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(StockLevel(id=uuid.uuid4(), item_id=item.id, warehouse_id=wh.id, qty=2))
            await db.flush()


# ── delete behaviour: the decisions worth pinning ───────────────────────────

@pytest.mark.asyncio
async def test_deleting_a_departed_staff_member_keeps_the_kit(db):
    """The legacy system had 14 of 35 kits assigned to someone who had left.
    A departing user must release the kit, never delete it — hence SET NULL
    rather than CASCADE on current_holder_user_id."""
    holder = await _user(db)
    kit = await _kit(db, current_holder_user_id=holder.id)

    await db.execute(delete(User).where(User.id == holder.id))
    await db.flush()
    # refresh(), not expire_all() + re-select: the FK was nulled by the
    # database, not the ORM, and under asyncpg an expired attribute read
    # outside a greenlet raises MissingGreenlet.
    await db.refresh(kit)

    assert kit.current_holder_user_id is None
    assert kit.current_location_id is not None, "it still belongs somewhere"


@pytest.mark.asyncio
async def test_a_user_who_recorded_a_movement_cannot_be_deleted(db):
    """movements.created_by is RESTRICT: a custody record with nobody behind
    it is worthless, and inventory history is exactly what you reach for when
    something has gone missing. Same reasoning as
    attendance_records.recorded_by_user_id."""
    actor = await _user(db)
    kit = await _kit(db)
    db.add(Movement(id=uuid.uuid4(), kit_id=kit.id, reason="issue", created_by=actor.id))
    await db.flush()

    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(delete(User).where(User.id == actor.id))
            await db.flush()


@pytest.mark.asyncio
async def test_deleting_a_session_keeps_the_movement(db):
    """Sessions are deletable (W6.5-2). Deleting one must not destroy the
    record of which physical kit went where — SET NULL, not CASCADE."""
    session = await _session(db)
    kit = await _kit(db)
    actor = await _user(db)
    mv = Movement(
        id=uuid.uuid4(), kit_id=kit.id, reason="issue",
        created_by=actor.id, session_id=session.id,
    )
    db.add(mv)
    await db.flush()

    await db.execute(delete(Session).where(Session.id == session.id))
    await db.flush()
    await db.refresh(mv)

    assert mv.session_id is None, "the session is gone but the custody record is not"
    assert mv.kit_id == kit.id


@pytest.mark.asyncio
async def test_deleting_a_kit_removes_its_contents(db):
    """kit_items is CASCADE — the contents of a kit have no meaning without
    the kit. (Whether a kit should be deletable at all is a service-layer
    question; the schema allows it.)"""
    kit = await _kit(db)
    item = await _item(db)
    db.add(KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=item.id, qty=1))
    await db.flush()

    await db.execute(delete(Kit).where(Kit.id == kit.id))
    await db.flush()

    left = (await db.execute(select(KitItem).where(KitItem.kit_id == kit.id))).scalars().all()
    assert left == []


@pytest.mark.asyncio
async def test_a_catalogue_item_in_use_cannot_be_deleted(db):
    """items -> kit_items is RESTRICT: deleting "EPS Board" from the catalogue
    must not silently empty every kit that contains one."""
    kit = await _kit(db)
    item = await _item(db)
    db.add(KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=item.id, qty=1))
    await db.flush()

    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(delete(Item).where(Item.id == item.id))
            await db.flush()


# ── column widths actually fit the values we intend to store ────────────────

@pytest.mark.asyncio
async def test_real_world_values_fit_their_columns(db):
    """The R1-2 lesson: widths that look fine in DDL review can fail on the
    first real insert. Every value here is one this system will genuinely
    store."""
    loc = Location(id=uuid.uuid4(), name="SpacePoint Main Warehouse — Dubai", country="AE")
    db.add(loc)
    await db.flush()
    wh = Warehouse(id=uuid.uuid4(), location_id=loc.id, name="SpacePoint Main Warehouse — Dubai")
    db.add(wh)
    tpl = KitTemplate(id=uuid.uuid4(), name="Mission Payload Kit v1", code="MPKIT")
    db.add(tpl)
    item = Item(
        id=uuid.uuid4(),
        name="M3 20.6mm Brass Standoff",   # longest real component name
        category="mechanical",              # longest category
    )
    db.add(item)
    await db.flush()

    kit = Kit(
        id=uuid.uuid4(), template_id=tpl.id,
        label="SP-SATKIT-0001",
        public_token=uuid.uuid4().hex * 2,  # 64 chars, the max
        status="retired",
        current_location_id=loc.id,
        current_warehouse_id=wh.id,
    )
    db.add(kit)
    actor = await _user(db)
    await db.flush()

    db.add(Movement(
        id=uuid.uuid4(), kit_id=kit.id,
        reason="writeoff",                  # longest reason
        due_back_on=date.today() + timedelta(days=14),
        created_by=actor.id,
    ))
    await db.flush()
