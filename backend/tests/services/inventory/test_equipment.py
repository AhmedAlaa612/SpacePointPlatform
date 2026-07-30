"""Non-kit equipment taken to a session (I2-7).

What these tests pin is mostly *derivation* — that the collection point comes
from the assigned kits and is never guessed when it can't be derived — plus
the fact that this adds no new machinery: every pickup is an ordinary movement
on the one ledger.
"""

import uuid
from datetime import date

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
    pickup_location,
    return_equipment,
    search_equipment,
    session_equipment,
    take_equipment,
)


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


async def _stocked(db, loc, name="Mic speaker", qty=3, returnable=True) -> Item:
    item = Item(
        id=uuid.uuid4(), name=f"{name} {uuid.uuid4().hex[:4]}", category="other",
        is_consumable=False, returnable_default=returnable,
    )
    db.add(item)
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=item.id, location_id=loc.id, qty=qty))
    await db.flush()
    return item


# ── deriving the collection point ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_collection_point_comes_from_the_assigned_kits(db):
    """The operator's whole reason for having no `pickup_location_id` column:
    ops moves the kit to the session's warehouse first, so the kit's location
    already *is* the collection point."""
    ops = await _user(db, "operations")
    loc = await _loc(db, "Abu Dhabi hub")
    session = await _session(db)
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)

    derived = await pickup_location(db, session.id)
    assert derived is not None and derived.id == loc.id


@pytest.mark.asyncio
async def test_a_session_with_no_kits_has_nothing_to_derive_from(db):
    """The rare no-kit session — an instructor taking only a speaker and some
    T-shirts. We ask rather than invent."""
    session = await _session(db)
    assert await pickup_location(db, session.id) is None


@pytest.mark.asyncio
async def test_kits_in_two_places_do_not_silently_pick_one(db):
    """Returning an arbitrary one of several would be exactly the field that
    quietly disagrees with reality that dropping the column avoided."""
    ops = await _user(db, "operations")
    dubai, sharjah = await _loc(db, "Dubai"), await _loc(db, "Sharjah")
    session = await _session(db)
    a, b = await _kit(db, dubai), await _kit(db, sharjah)
    await assign_kits(db, session_id=session.id, kit_ids=[a.id, b.id], actor_user_id=ops.id)

    assert await pickup_location(db, session.id) is None


# ── the search box ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_empty_query_returns_nothing_rather_than_the_whole_shelf(db):
    """§G is explicit: the section starts empty. A co-working space may hold
    forty item types and most sessions take nothing extra."""
    loc = await _loc(db)
    await _stocked(db, loc)
    assert await search_equipment(db, location_id=loc.id, q="") == []
    assert await search_equipment(db, location_id=loc.id, q="m") == []


@pytest.mark.asyncio
async def test_search_only_offers_what_is_actually_on_that_shelf(db):
    """Offering something the register says isn't there invites a pickup
    `move()` refuses at the last step, after it has all been typed in."""
    here, elsewhere = await _loc(db, "Dubai"), await _loc(db, "Sharjah")
    mine = await _stocked(db, here, name="Battery charger")
    theirs = await _stocked(db, elsewhere, name="Battery charger spare")

    found = await search_equipment(db, location_id=here.id, q="battery")
    assert [row["item_id"] for row in found] == [mine.id]
    assert theirs.id not in {row["item_id"] for row in found}


@pytest.mark.asyncio
async def test_an_item_on_the_shelf_at_zero_is_not_offered(db):
    loc = await _loc(db)
    await _stocked(db, loc, name="Stickers", qty=0)
    assert await search_equipment(db, location_id=loc.id, q="stickers") == []


# ── taking and bringing back ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_taking_equipment_is_an_ordinary_movement_and_moves_the_stock(db):
    """The point of I2-7 being schema-free: this rides the same ledger as kits
    and merch."""
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=instructor)
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    item = await _stocked(db, loc, qty=3)

    [movement] = await take_equipment(
        db, session_id=session.id, actor_user_id=instructor.id, lines=[(item.id, 2)]
    )

    assert movement.reason == "issue"
    assert movement.from_location_id == loc.id      # derived, not passed
    assert movement.to_user_id == instructor.id
    assert movement.session_id == session.id
    assert movement.due_back_on is None             # same-day kit; the post prompt asks

    level = (await db.execute(
        select(StockLevel).where(
            StockLevel.item_id == item.id, StockLevel.location_id == loc.id
        )
    )).scalars().first()
    assert level.qty == 1


@pytest.mark.asyncio
async def test_taking_more_than_the_shelf_holds_is_refused(db):
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=instructor)
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    item = await _stocked(db, loc, qty=1)

    with pytest.raises(HTTPException) as exc:
        await take_equipment(
            db, session_id=session.id, actor_user_id=instructor.id, lines=[(item.id, 5)]
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_a_no_kit_session_must_be_told_where_and_then_works(db):
    """The uncommon path: nothing to derive from, so one dropdown appears."""
    instructor = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=instructor)
    item = await _stocked(db, loc, qty=2)

    with pytest.raises(HTTPException) as exc:
        await take_equipment(
            db, session_id=session.id, actor_user_id=instructor.id, lines=[(item.id, 1)]
        )
    assert exc.value.status_code == 409

    [movement] = await take_equipment(
        db, session_id=session.id, actor_user_id=instructor.id,
        lines=[(item.id, 1)], location_id=loc.id,
    )
    assert movement.from_location_id == loc.id


@pytest.mark.asyncio
async def test_the_post_session_list_nets_returns_against_pickups(db):
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=instructor)
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    item = await _stocked(db, loc, qty=5)

    await take_equipment(
        db, session_id=session.id, actor_user_id=instructor.id, lines=[(item.id, 3)]
    )
    [line] = await session_equipment(db, session_id=session.id, user_id=instructor.id)
    assert (line["qty_taken"], line["qty_returned"], line["outstanding"]) == (3, 0, 3)
    assert line["returnable"] is True

    await return_equipment(
        db, session_id=session.id, actor_user_id=instructor.id, lines=[(item.id, 2)]
    )
    [line] = await session_equipment(db, session_id=session.id, user_id=instructor.id)
    assert (line["qty_taken"], line["qty_returned"], line["outstanding"]) == (3, 2, 1)


@pytest.mark.asyncio
async def test_returning_later_leaves_the_line_outstanding(db):
    """"Returning later" is the absence of a return, not a recorded state —
    the line stays visible because that is where the thing actually is."""
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=instructor)
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    item = await _stocked(db, loc, qty=2)

    await take_equipment(
        db, session_id=session.id, actor_user_id=instructor.id, lines=[(item.id, 1)]
    )
    await return_equipment(
        db, session_id=session.id, actor_user_id=instructor.id, lines=[]
    )

    [line] = await session_equipment(db, session_id=session.id, user_id=instructor.id)
    assert line["outstanding"] == 1


@pytest.mark.asyncio
async def test_giving_back_more_than_you_took_is_refused(db):
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=instructor)
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    item = await _stocked(db, loc, qty=4)

    await take_equipment(
        db, session_id=session.id, actor_user_id=instructor.id, lines=[(item.id, 1)]
    )
    with pytest.raises(HTTPException) as exc:
        await return_equipment(
            db, session_id=session.id, actor_user_id=instructor.id, lines=[(item.id, 2)]
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_returning_puts_the_stock_back_on_the_derived_shelf(db):
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=instructor)
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    item = await _stocked(db, loc, qty=2)

    await take_equipment(
        db, session_id=session.id, actor_user_id=instructor.id, lines=[(item.id, 2)]
    )
    [movement] = await return_equipment(
        db, session_id=session.id, actor_user_id=instructor.id, lines=[(item.id, 2)]
    )

    assert movement.reason == "return"
    assert movement.from_user_id == instructor.id
    assert movement.to_location_id == loc.id
    assert movement.session_id == session.id

    level = (await db.execute(
        select(StockLevel).where(
            StockLevel.item_id == item.id, StockLevel.location_id == loc.id
        )
    )).scalars().first()
    assert level.qty == 2


@pytest.mark.asyncio
async def test_one_instructors_pickup_is_not_anothers(db):
    """Two people teach the same session; each answers for what they took."""
    ops = await _user(db, "operations")
    lead = await _user(db, "instructor")
    co = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=lead)
    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=session.id, user_id=co.id, role="co"
    ))
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    item = await _stocked(db, loc, qty=5)

    await take_equipment(
        db, session_id=session.id, actor_user_id=lead.id, lines=[(item.id, 2)]
    )

    assert len(await session_equipment(db, session_id=session.id, user_id=lead.id)) == 1
    assert await session_equipment(db, session_id=session.id, user_id=co.id) == []


@pytest.mark.asyncio
async def test_equipment_and_kits_share_the_one_ledger(db):
    """The payoff of collapsing four legacy tables into `movements`: an
    equipment pickup is queryable next to everything else that moved."""
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    loc = await _loc(db)
    session = await _session(db, lead=instructor)
    kit = await _kit(db, loc)
    await assign_kits(db, session_id=session.id, kit_ids=[kit.id], actor_user_id=ops.id)
    item = await _stocked(db, loc, qty=2)

    await take_equipment(
        db, session_id=session.id, actor_user_id=instructor.id, lines=[(item.id, 1)]
    )

    rows = (await db.execute(
        select(Movement).where(Movement.session_id == session.id)
    )).scalars().all()
    assert len(rows) == 1 and rows[0].item_id == item.id
