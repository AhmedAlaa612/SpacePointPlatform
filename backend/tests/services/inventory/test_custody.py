"""Custody handover and merchandise (I2-3/I2-4).

The confirmation step never blocks anything, so what these tests actually pin
is that its *absence* stays visible — "marked out, never collected" and
"handed back, never received" are where things go missing.
"""

import uuid
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.inventory import Item, Kit, KitTemplate, Location, Movement, StockLevel
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.inventory import (
    assign_kits,
    confirm_collected,
    held_by_user,
    issue_merch,
    issue_session_kits,
    return_merch,
    return_session_kits,
    unconfirmed_handovers,
)


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
            id=uuid.uuid4(), session_id=session.id, user_id=lead.id, role="lead"
        ))
        await db.flush()
    return session


async def _kit(db, loc) -> Kit:
    tpl = KitTemplate(id=uuid.uuid4(), name="SatKit", code=f"T{uuid.uuid4().hex[:5]}")
    db.add(tpl)
    await db.flush()
    kit = Kit(
        id=uuid.uuid4(), template_id=tpl.id, label=f"SP-K-{uuid.uuid4().hex[:6]}",
        public_token=uuid.uuid4().hex * 2, current_location_id=loc.id,
    )
    db.add(kit)
    await db.flush()
    return kit


# ── the four legs ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_issuing_defaults_to_the_lead_instructor(db):
    ops = await _user(db)
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=lead)
    kit_a, kit_b = await _kit(db, loc), await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit_a.id, kit_b.id], actor_user_id=ops.id)

    movements = await issue_session_kits(db, session_id=session.id, actor_user_id=ops.id)

    assert len(movements) == 2
    assert kit_a.current_holder_user_id == lead.id
    assert kit_b.current_holder_user_id == lead.id
    assert kit_a.current_location_id == loc.id, "still belongs to Dubai while it's out"


@pytest.mark.asyncio
async def test_issuing_with_nobody_teaching_says_so(db):
    ops = await _user(db)
    loc = await _loc(db)
    session = await _session(db)
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)

    with pytest.raises(HTTPException) as exc:
        await issue_session_kits(db, session_id=session.id, actor_user_id=ops.id)
    assert exc.value.status_code == 409
    assert "assign an instructor" in exc.value.detail


@pytest.mark.asyncio
async def test_issuing_twice_does_not_duplicate(db):
    """Ops tapping the button again must not write a second handover row."""
    ops = await _user(db)
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=lead)
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)

    await issue_session_kits(db, session_id=session.id, actor_user_id=ops.id)
    second = await issue_session_kits(db, session_id=session.id, actor_user_id=ops.id)
    assert second == []


@pytest.mark.asyncio
async def test_confirming_collection_is_idempotent(db):
    ops = await _user(db)
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=lead)
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    await issue_session_kits(db, session_id=session.id, actor_user_id=ops.id)

    first = await confirm_collected(db, session_id=session.id, user_id=lead.id)
    assert len(first) == 1 and first[0].confirmed_at is not None

    second = await confirm_collected(db, session_id=session.id, user_id=lead.id)
    assert second == [], "nothing left to confirm — and that is not an error"


@pytest.mark.asyncio
async def test_an_unconfirmed_handover_stays_visible(db):
    """The gap is the product: marked out, never acknowledged."""
    ops = await _user(db)
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=lead)
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    await issue_session_kits(db, session_id=session.id, actor_user_id=ops.id)

    pending = await unconfirmed_handovers(db)
    assert [m.kit_id for m, _name in pending] == [kit.id]

    await confirm_collected(db, session_id=session.id, user_id=lead.id)
    assert await unconfirmed_handovers(db) == []


@pytest.mark.asyncio
async def test_returning_kits_puts_them_somewhere_specific(db):
    ops = await _user(db)
    lead = await _user(db, "instructor")
    dubai, main = await _loc(db), await _loc(db, name="Main")
    session = await _session(db, lead=lead)
    kit = await _kit(db, dubai)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    await issue_session_kits(db, session_id=session.id, actor_user_id=ops.id)

    returned = await return_session_kits(
        db, session_id=session.id, actor_user_id=ops.id, to_location_id=main.id
    )

    assert len(returned) == 1
    assert kit.current_holder_user_id is None
    assert kit.current_location_id == main.id, "came back to Main, not to where it started"


@pytest.mark.asyncio
async def test_returning_when_nothing_is_out_returns_nothing(db):
    ops = await _user(db)
    loc = await _loc(db)
    session = await _session(db)
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)

    assert await return_session_kits(
        db, session_id=session.id, actor_user_id=ops.id, to_location_id=loc.id
    ) == []


# ── merchandise ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_vest_is_expected_back_and_a_tshirt_is_not(db):
    """The item's own default, so ops isn't answering this fifty times."""
    ops = await _user(db)
    person = await _user(db, "instructor")
    loc = await _loc(db)
    vest = Item(id=uuid.uuid4(), name="Vest (L)", category="merch", returnable_default=True)
    shirt = Item(id=uuid.uuid4(), name="T-Shirt (M)", category="merch", returnable_default=False)
    db.add_all([vest, shirt])
    await db.flush()
    db.add_all([
        StockLevel(id=uuid.uuid4(), item_id=vest.id, location_id=loc.id, qty=5),
        StockLevel(id=uuid.uuid4(), item_id=shirt.id, location_id=loc.id, qty=5),
    ])
    await db.flush()
    due = date.today() + timedelta(days=30)

    vest_mv = await issue_merch(
        db, actor_user_id=ops.id, item_id=vest.id, to_user_id=person.id,
        from_location_id=loc.id, due_back_on=due,
    )
    shirt_mv = await issue_merch(
        db, actor_user_id=ops.id, item_id=shirt.id, to_user_id=person.id,
        from_location_id=loc.id, due_back_on=due,
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
    vest = Item(id=uuid.uuid4(), name="Vest (L)", category="merch", returnable_default=True)
    db.add(vest)
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=vest.id, location_id=loc.id, qty=10))
    await db.flush()

    await issue_merch(db, actor_user_id=ops.id, item_id=vest.id, to_user_id=person.id,
                      from_location_id=loc.id, qty=2)
    assert [(h["item_name"], h["qty"]) for h in await held_by_user(db, person.id)] == [("Vest (L)", 2)]

    await return_merch(db, actor_user_id=ops.id, item_id=vest.id, from_user_id=person.id,
                       to_location_id=loc.id, qty=1)
    assert [(h["item_name"], h["qty"]) for h in await held_by_user(db, person.id)] == [("Vest (L)", 1)]

    await return_merch(db, actor_user_id=ops.id, item_id=vest.id, from_user_id=person.id,
                       to_location_id=loc.id, qty=1)
    assert await held_by_user(db, person.id) == [], "nothing held shows nothing, not a zero row"


@pytest.mark.asyncio
async def test_you_cannot_give_back_more_than_you_have(db):
    ops = await _user(db)
    person = await _user(db, "instructor")
    loc = await _loc(db)
    vest = Item(id=uuid.uuid4(), name="Vest (M)", category="merch", returnable_default=True)
    db.add(vest)
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=vest.id, location_id=loc.id, qty=10))
    await db.flush()
    await issue_merch(db, actor_user_id=ops.id, item_id=vest.id, to_user_id=person.id,
                      from_location_id=loc.id, qty=1)

    with pytest.raises(HTTPException) as exc:
        await return_merch(db, actor_user_id=ops.id, item_id=vest.id, from_user_id=person.id,
                           to_location_id=loc.id, qty=3)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_issuing_merch_takes_it_off_the_shelf(db):
    ops = await _user(db)
    person = await _user(db, "instructor")
    loc = await _loc(db)
    vest = Item(id=uuid.uuid4(), name="Vest (S)", category="merch", returnable_default=True)
    db.add(vest)
    await db.flush()
    level = StockLevel(id=uuid.uuid4(), item_id=vest.id, location_id=loc.id, qty=4)
    db.add(level)
    await db.flush()

    await issue_merch(db, actor_user_id=ops.id, item_id=vest.id, to_user_id=person.id,
                      from_location_id=loc.id, qty=2)
    assert level.qty == 2


@pytest.mark.asyncio
async def test_merch_and_kits_share_one_ledger(db):
    """The reason four legacy tables became one."""
    ops = await _user(db)
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=lead)
    kit = await _kit(db, loc)
    vest = Item(id=uuid.uuid4(), name="Vest (XL)", category="merch", returnable_default=True)
    db.add(vest)
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=vest.id, location_id=loc.id, qty=3))
    await db.flush()

    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    await issue_session_kits(db, session_id=session.id, actor_user_id=ops.id)
    await issue_merch(db, actor_user_id=ops.id, item_id=vest.id, to_user_id=lead.id,
                      from_location_id=loc.id)

    to_them = (await db.execute(
        select(Movement).where(Movement.to_user_id == lead.id)
    )).scalars().all()
    assert len(to_them) == 2
    assert {m.kit_id is not None for m in to_them} == {True, False}
