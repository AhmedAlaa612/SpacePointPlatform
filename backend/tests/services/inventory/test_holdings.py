"""What one person is holding, and giving it back themselves (2026-08-01).

A kit's holder and an item's outstanding ledger balance are the source of
truth already; these tests pin that "return later" on a session kit is a
real hold (not just a status label), that "returned" restocks immediately
with no ops step, and that the holder — not just ops — can bring either kind
of thing back on their own.
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from app.models.inventory import Item, Kit, KitTemplate, Location, StockLevel, Warehouse
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.inventory import (
    assign_kits,
    default_kit_return_warehouse,
    issue_merch,
    mark_kits_returned,
    my_held_items,
    return_own_item,
    return_own_kit,
    take_equipment,
)


async def _role_id(db, name: str = "Lead Facilitator"):
    from sqlalchemy import select

    from app.models.sessions.delivery_role import DeliveryRole

    return await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))


async def _user(db, *roles: str) -> User:
    u = User(
        id=uuid.uuid4(), full_name=f"P{uuid.uuid4().hex[:4]}",
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) or ["instructor"], status="active",
    )
    db.add(u)
    await db.flush()
    return u


async def _loc(db, name="Dubai") -> Location:
    loc = Location(id=uuid.uuid4(), name=name, country="AE")
    db.add(loc)
    await db.flush()
    return loc


async def _wh(db, loc, name=None) -> Warehouse:
    wh = Warehouse(id=uuid.uuid4(), location_id=loc.id, name=name or f"{loc.name} Main")
    db.add(wh)
    await db.flush()
    return wh


async def _session(db, *, lead: User) -> Session:
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="P",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="C", status="running")
    db.add(cohort)
    await db.flush()
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today())
    db.add(session)
    await db.flush()
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=lead.id, role_id=await _role_id(db)))
    await db.flush()
    return session


async def _kit(db, wh) -> Kit:
    tpl = KitTemplate(id=uuid.uuid4(), name="SatKit", code=f"T{uuid.uuid4().hex[:5]}")
    db.add(tpl)
    await db.flush()
    kit = Kit(
        id=uuid.uuid4(), template_id=tpl.id, label=f"SP-K-{uuid.uuid4().hex[:6]}",
        public_token=uuid.uuid4().hex * 2, current_location_id=wh.location_id,
        current_warehouse_id=wh.id,
    )
    db.add(kit)
    await db.flush()
    return kit


# ── kits: return_later is a real hold, returned restocks immediately ────────

@pytest.mark.asyncio
async def test_return_later_puts_the_kit_in_the_instructors_hands(db):
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead=lead)
    kit = await _kit(db, wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)

    await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=True)

    assert kit.current_holder_user_id == lead.id
    assert kit.current_warehouse_id == wh.id, "still belongs to Dubai while it's out"
    assert kit.current_location_id == loc.id


@pytest.mark.asyncio
async def test_returned_restocks_to_the_session_warehouse_immediately(db):
    """No ops step, no location picker — the session already has a
    warehouse, so there's nothing left to ask."""
    lead = await _user(db, "instructor")
    dubai, main = await _loc(db), await _loc(db, name="Main")
    dubai_wh, main_wh = await _wh(db, dubai), await _wh(db, main)
    session = await _session(db, lead=lead)
    session.warehouse_id = main_wh.id
    kit = await _kit(db, dubai_wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)
    await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=True)

    await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=False)

    assert kit.current_holder_user_id is None
    assert kit.current_warehouse_id == main_wh.id
    assert kit.current_location_id == main.id


@pytest.mark.asyncio
async def test_flipping_returned_kit_back_to_later_re_holds_it(db):
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead=lead)
    session.warehouse_id = wh.id
    kit = await _kit(db, wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)
    await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=True)
    await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=False)
    assert kit.current_holder_user_id is None

    await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=True)
    assert kit.current_holder_user_id == lead.id


# ── self-serve returns ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_default_kit_return_warehouse_resolves_to_the_session(db):
    lead = await _user(db, "instructor")
    dubai, main = await _loc(db), await _loc(db, name="Main")
    dubai_wh, main_wh = await _wh(db, dubai), await _wh(db, main)
    session = await _session(db, lead=lead)
    session.warehouse_id = main_wh.id
    kit = await _kit(db, dubai_wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)
    await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=True)

    assert await default_kit_return_warehouse(db, kit) == main_wh.id


@pytest.mark.asyncio
async def test_holder_can_return_their_own_kit_without_ops(db):
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead=lead)
    session.warehouse_id = wh.id
    kit = await _kit(db, wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)
    await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=True)

    await return_own_kit(db, actor_user_id=lead.id, kit_id=kit.id)

    assert kit.current_holder_user_id is None
    assert kit.current_warehouse_id == wh.id


@pytest.mark.asyncio
async def test_cannot_return_a_kit_you_do_not_hold(db):
    lead = await _user(db, "instructor")
    outsider = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead=lead)
    kit = await _kit(db, wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)
    await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=True)

    with pytest.raises(HTTPException) as exc:
        await return_own_kit(db, actor_user_id=outsider.id, kit_id=kit.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_holder_can_return_their_own_item_and_it_clears_the_later_flag(db):
    ops = await _user(db, "operations")
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead=lead)
    session.warehouse_id = wh.id
    kit = await _kit(db, wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    item = Item(
        id=uuid.uuid4(), name="Mic speaker", category="other",
        returnable_default=True,
    )
    db.add(item)
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=item.id, warehouse_id=wh.id, qty=2))
    await db.flush()

    await take_equipment(db, session_id=session.id, actor_user_id=lead.id, lines=[(item.id, 1)])

    [held] = await my_held_items(db, lead.id)
    assert held["default_warehouse_id"] == wh.id

    await return_own_item(db, actor_user_id=lead.id, item_id=item.id, qty=1)
    assert await my_held_items(db, lead.id) == []


@pytest.mark.asyncio
async def test_directly_assigned_merch_can_be_self_returned_too(db):
    """"Ops can assign kits and items directly to people, same flow
    applies" — an item that never touched a session works exactly the same
    way, defaulting to wherever it was issued from."""
    ops = await _user(db, "operations")
    person = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    vest = Item(id=uuid.uuid4(), name="Vest (L)", category="merch", returnable_default=True)
    db.add(vest)
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=vest.id, warehouse_id=wh.id, qty=5))
    await db.flush()

    await issue_merch(db, actor_user_id=ops.id, item_id=vest.id, to_user_id=person.id, from_warehouse_id=wh.id)

    [held] = await my_held_items(db, person.id)
    assert held["default_warehouse_id"] == wh.id

    await return_own_item(db, actor_user_id=person.id, item_id=vest.id, qty=1)
    assert await my_held_items(db, person.id) == []
