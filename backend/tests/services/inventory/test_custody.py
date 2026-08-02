"""Session kit receipts and merchandise (I2-3/I2-4).

Kits have no custody leg: assigning one to a session is the whole story
until the instructor reports on it. These tests pin the receive/return/
confirm report instead of a movement ledger, and the fact that ops's
confirmation is a separate, optional step from actually moving anything.
"""

import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException

from app.models.inventory import Item, Kit, KitTemplate, Location, StockLevel, Warehouse
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.inventory import (
    assign_kits,
    confirm_kit_returns,
    held_by_user,
    issue_merch,
    mark_kits_received,
    mark_kits_returned,
    return_merch,
)


async def _role_id(db, name: str = "Lead Facilitator"):
    """I5-3: roles are rows now. The three are seeded by migration
    `c2a7b49e0022`, so tests look them up rather than inventing their own."""
    from sqlalchemy import select

    from app.models.sessions.delivery_role import DeliveryRole

    return await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))



async def _user(db, *roles: str) -> User:
    u = User(
        id=uuid.uuid4(), full_name=f"P{uuid.uuid4().hex[:4]}",
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) or ["operations"], status="active",
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


async def _session(db, *, lead: User | None = None) -> Session:
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
    if lead:
        db.add(SessionInstructor(
            id=uuid.uuid4(), session_id=session.id, user_id=lead.id, role_id=await _role_id(db)
        ))
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


# ── receiving and returning ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_receiving_marks_each_kit_and_is_repeatable(db):
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead=lead)
    kit_a, kit_b = await _kit(db, wh), await _kit(db, wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit_a.id, kit_b.id], actor_user_id=lead.id)

    rows = await mark_kits_received(db, session_id=session.id, kit_ids=[kit_a.id], actor_user_id=lead.id)
    assert len(rows) == 1 and rows[0].received_at is not None
    assert kit_a.current_warehouse_id == wh.id, "receiving is a report, not a move"

    # Tapping it again (e.g. select-all after one was already ticked) is fine.
    again = await mark_kits_received(db, session_id=session.id, kit_ids=[kit_a.id], actor_user_id=lead.id)
    assert again[0].received_at is not None


@pytest.mark.asyncio
async def test_receiving_an_unassigned_kit_is_a_404(db):
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead=lead)
    kit = await _kit(db, wh)  # never assigned

    with pytest.raises(HTTPException) as exc:
        await mark_kits_received(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_returning_records_a_report_no_warehouse_needed(db):
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead=lead)
    kit = await _kit(db, wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)

    rows = await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)
    assert rows[0].return_status == "returned"
    assert kit.current_warehouse_id == wh.id, "still just a report — nothing moved yet"


@pytest.mark.asyncio
async def test_returning_later_is_a_distinct_status(db):
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead=lead)
    kit = await _kit(db, wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)

    rows = await mark_kits_returned(
        db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=True, note="Next week"
    )
    assert rows[0].return_status == "return_later"
    assert rows[0].return_note == "Next week"


@pytest.mark.asyncio
async def test_changing_your_mind_either_way_is_fine(db):
    """Reporting "returned" then "actually later", or the reverse, is just
    overwriting the report — not a special case."""
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead=lead)
    kit = await _kit(db, wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)

    await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=False)
    flipped = await mark_kits_returned(
        db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=True
    )
    assert flipped[0].return_status == "return_later"

    back = await mark_kits_returned(
        db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=False
    )
    assert back[0].return_status == "returned"


@pytest.mark.asyncio
async def test_the_report_freezes_once_the_session_is_done(db):
    """Post-completion gate was removed per operator decision: instructors/ops
    can update kit returns even after session completion."""
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead=lead)
    kit = await _kit(db, wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)
    await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=True)

    from datetime import datetime, timezone
    session.completed_at = datetime.now(timezone.utc)
    await db.flush()

    res = await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id, later=False)
    assert res[0].return_status == "returned"


# ── ops confirming the report ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirming_before_a_report_exists_is_a_409(db):
    ops = await _user(db)
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead=lead)
    kit = await _kit(db, wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)

    with pytest.raises(HTTPException) as exc:
        await confirm_kit_returns(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_confirming_without_a_restock_warehouse_moves_nothing(db):
    ops = await _user(db)
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead=lead)
    kit = await _kit(db, wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)

    rows = await confirm_kit_returns(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    assert rows[0].ops_confirmed_at is not None
    assert kit.current_warehouse_id == wh.id, "confirming is not restocking"


@pytest.mark.asyncio
async def test_confirming_with_a_restock_warehouse_moves_the_kit(db):
    ops = await _user(db)
    lead = await _user(db, "instructor")
    dubai, main = await _loc(db), await _loc(db, name="Main")
    dubai_wh, main_wh = await _wh(db, dubai), await _wh(db, main)
    session = await _session(db, lead=lead)
    kit = await _kit(db, dubai_wh)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    await mark_kits_returned(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=lead.id)

    await confirm_kit_returns(
        db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id, restock_warehouse_id=main_wh.id
    )
    assert kit.current_warehouse_id == main_wh.id


# ── merchandise ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_vest_is_expected_back_and_a_tshirt_is_not(db):
    """The item's own default, so ops isn't answering this fifty times."""
    ops = await _user(db)
    person = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    vest = Item(id=uuid.uuid4(), name="Vest (L)", category="merch", returnable_default=True)
    shirt = Item(id=uuid.uuid4(), name="T-Shirt (M)", category="merch", returnable_default=False)
    db.add_all([vest, shirt])
    await db.flush()
    db.add_all([
        StockLevel(id=uuid.uuid4(), item_id=vest.id, warehouse_id=wh.id, qty=5),
        StockLevel(id=uuid.uuid4(), item_id=shirt.id, warehouse_id=wh.id, qty=5),
    ])
    await db.flush()
    due = date.today() + timedelta(days=30)

    vest_mv = await issue_merch(
        db, actor_user_id=ops.id, item_id=vest.id, to_user_id=person.id,
        from_warehouse_id=wh.id, due_back_on=due,
    )
    shirt_mv = await issue_merch(
        db, actor_user_id=ops.id, item_id=shirt.id, to_user_id=person.id,
        from_warehouse_id=wh.id, due_back_on=due,
    )

    assert vest_mv.due_back_on == due
    assert shirt_mv.due_back_on is None, (
        "a deadline on something nobody returns fills the overdue list with noise "
        "and stops it working for kits"
    )


@pytest.mark.asyncio
async def test_what_someone_holds_nets_out_returns(db):
    ops = await _user(db)
    person = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    vest = Item(id=uuid.uuid4(), name="Vest (L)", category="merch", returnable_default=True)
    db.add(vest)
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=vest.id, warehouse_id=wh.id, qty=10))
    await db.flush()

    await issue_merch(db, actor_user_id=ops.id, item_id=vest.id, to_user_id=person.id,
                      from_warehouse_id=wh.id, qty=2)
    assert [(h["item_name"], h["qty"]) for h in await held_by_user(db, person.id)] == [("Vest (L)", 2)]

    await return_merch(db, actor_user_id=ops.id, item_id=vest.id, from_user_id=person.id,
                       to_warehouse_id=wh.id, qty=1)
    assert [(h["item_name"], h["qty"]) for h in await held_by_user(db, person.id)] == [("Vest (L)", 1)]

    await return_merch(db, actor_user_id=ops.id, item_id=vest.id, from_user_id=person.id,
                       to_warehouse_id=wh.id, qty=1)
    assert await held_by_user(db, person.id) == [], "nothing held shows nothing, not a zero row"


@pytest.mark.asyncio
async def test_held_by_user_carries_the_variant_label(db):
    """The point of grouping T-Shirt sizes for browsing: someone holding a
    variant is still identified by which one — the ledger keys on this
    item's own id regardless of grouping, and the label rides along so a
    holdings screen can say "T-Shirt · L" instead of just "T-Shirt"."""
    ops = await _user(db)
    person = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    shirt_l = Item(
        id=uuid.uuid4(), name="T-Shirt L", category="merch", returnable_default=False,
        variant_group="T-Shirt", variant_label="L",
    )
    db.add(shirt_l)
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=shirt_l.id, warehouse_id=wh.id, qty=5))
    await db.flush()

    await issue_merch(db, actor_user_id=ops.id, item_id=shirt_l.id, to_user_id=person.id, from_warehouse_id=wh.id)
    held = await held_by_user(db, person.id)
    assert held == [{
        "item_id": shirt_l.id, "item_name": "T-Shirt L",
        "variant_group": "T-Shirt", "variant_label": "L",
        "qty": 1, "due_back_on": None,
    }]


@pytest.mark.asyncio
async def test_you_cannot_give_back_more_than_you_have(db):
    ops = await _user(db)
    person = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    vest = Item(id=uuid.uuid4(), name="Vest (M)", category="merch", returnable_default=True)
    db.add(vest)
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=vest.id, warehouse_id=wh.id, qty=10))
    await db.flush()
    await issue_merch(db, actor_user_id=ops.id, item_id=vest.id, to_user_id=person.id,
                      from_warehouse_id=wh.id, qty=1)

    with pytest.raises(HTTPException) as exc:
        await return_merch(db, actor_user_id=ops.id, item_id=vest.id, from_user_id=person.id,
                           to_warehouse_id=wh.id, qty=3)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_issuing_merch_takes_it_off_the_shelf(db):
    ops = await _user(db)
    person = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    vest = Item(id=uuid.uuid4(), name="Vest (S)", category="merch", returnable_default=True)
    db.add(vest)
    await db.flush()
    level = StockLevel(id=uuid.uuid4(), item_id=vest.id, warehouse_id=wh.id, qty=4)
    db.add(level)
    await db.flush()

    await issue_merch(db, actor_user_id=ops.id, item_id=vest.id, to_user_id=person.id,
                      from_warehouse_id=wh.id, qty=2)
    assert level.qty == 2
