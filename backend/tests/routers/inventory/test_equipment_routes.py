"""Equipment pickup over HTTP (I2-7).

Redis-free on the shared `client`. What matters here is the guard: recording
equipment is a self-report by the person teaching, so the endpoints have to be
reachable by an instructor — and reachable by *only* the instructors on that
session, with an unrelated one getting 404 rather than 403.
"""

import uuid
from datetime import date

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.inventory import Item, Kit, KitTemplate, Location, StockLevel, Warehouse
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User


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
        password_hash=get_password_hash("x"), roles=list(roles), status="active",
    )
    db.add(u)
    await db.flush()
    return u


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


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


async def _kit(db, wh) -> Kit:
    tpl = KitTemplate(id=uuid.uuid4(), name="SatKit v1", code=f"T{uuid.uuid4().hex[:5]}")
    db.add(tpl)
    await db.flush()
    kit = Kit(
        id=uuid.uuid4(), template_id=tpl.id, label=f"SP-SATKIT-{uuid.uuid4().hex[:4]}",
        public_token=uuid.uuid4().hex * 2, current_location_id=wh.location_id,
        current_warehouse_id=wh.id,
    )
    db.add(kit)
    await db.flush()
    return kit


async def _session(db, lead: User) -> Session:
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


async def _stocked(db, wh, name="Mic speaker", qty=3, returnable=True) -> Item:
    item = Item(
        id=uuid.uuid4(), name=f"{name} {uuid.uuid4().hex[:4]}", category="other",
        returnable_default=returnable,
    )
    db.add(item)
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=item.id, warehouse_id=wh.id, qty=qty))
    await db.flush()
    return item


async def _assign(db, client, session, kit, ops):
    r = await client.put(
        f"/inventory/sessions/{session.id}/kits",
        json={"kit_ids": [str(kit.id)]}, headers=_headers(ops),
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_the_section_reports_the_derived_collection_point(client, db):
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    loc = await _loc(db, "Abu Dhabi hub")
    wh = await _wh(db, loc)
    session = await _session(db, instructor)
    kit = await _kit(db, wh)
    await _assign(db, client, session, kit, ops)

    r = await client.get(
        f"/inventory/sessions/{session.id}/equipment", headers=_headers(instructor)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["warehouse_id"] == str(wh.id)
    assert body["warehouse_name"] == wh.name
    assert body["lines"] == [] and body["outstanding_count"] == 0


@pytest.mark.asyncio
async def test_a_no_kit_session_reports_no_collection_point(client, db):
    """Which is what tells the UI to show its one dropdown, on the uncommon
    path only."""
    instructor = await _user(db, "instructor")
    session = await _session(db, instructor)

    r = await client.get(
        f"/inventory/sessions/{session.id}/equipment", headers=_headers(instructor)
    )
    assert r.status_code == 200
    assert r.json()["warehouse_id"] is None


@pytest.mark.asyncio
async def test_an_instructor_can_record_and_return_their_own_pickup(client, db):
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, instructor)
    kit = await _kit(db, wh)
    await _assign(db, client, session, kit, ops)
    item = await _stocked(db, wh, qty=4)

    r = await client.post(
        f"/inventory/sessions/{session.id}/equipment/take",
        json={"lines": [{"item_id": str(item.id), "qty": 2}]},
        headers=_headers(instructor),
    )
    assert r.status_code == 201
    assert r.json()[0]["from_warehouse_id"] == str(wh.id)

    r = await client.get(
        f"/inventory/sessions/{session.id}/equipment", headers=_headers(instructor)
    )
    assert r.json()["lines"][0]["outstanding"] == 2
    assert r.json()["outstanding_count"] == 1

    r = await client.post(
        f"/inventory/sessions/{session.id}/equipment/return",
        json={"lines": [{"item_id": str(item.id), "qty": 2}]},
        headers=_headers(instructor),
    )
    assert r.status_code == 201

    r = await client.get(
        f"/inventory/sessions/{session.id}/equipment", headers=_headers(instructor)
    )
    assert r.json()["lines"][0]["outstanding"] == 0
    assert r.json()["outstanding_count"] == 0


@pytest.mark.asyncio
async def test_search_defaults_to_the_whole_shelf_and_only_offers_that_shelf(client, db):
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, instructor)
    kit = await _kit(db, wh)
    await _assign(db, client, session, kit, ops)
    item = await _stocked(db, wh, name="Battery charger")

    r = await client.get(
        f"/inventory/sessions/{session.id}/equipment/search", headers=_headers(instructor)
    )
    assert r.status_code == 200
    assert [row["item_id"] for row in r.json()] == [str(item.id)]

    r = await client.get(
        f"/inventory/sessions/{session.id}/equipment/search",
        params={"q": "battery"}, headers=_headers(instructor),
    )
    assert [row["item_id"] for row in r.json()] == [str(item.id)]

    r = await client.get(
        f"/inventory/sessions/{session.id}/equipment/search",
        params={"q": "zzz"}, headers=_headers(instructor),
    )
    assert r.json() == []


@pytest.mark.asyncio
async def test_an_unrelated_instructor_gets_404_not_403(client, db):
    """The don't-leak-existence rule — same as the rest of the delivery flow."""
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    stranger = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, instructor)
    kit = await _kit(db, wh)
    await _assign(db, client, session, kit, ops)
    item = await _stocked(db, wh)

    r = await client.get(
        f"/inventory/sessions/{session.id}/equipment", headers=_headers(stranger)
    )
    assert r.status_code == 404

    r = await client.post(
        f"/inventory/sessions/{session.id}/equipment/take",
        json={"lines": [{"item_id": str(item.id), "qty": 1}]},
        headers=_headers(stranger),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_a_storekeeper_cannot_reach_the_equipment_endpoints(client, db):
    """The storekeeper's narrowness is invisible negative space — it holds only
    because no guard lists the role. These endpoints must not become the
    exception."""
    ops = await _user(db, "operations")
    instructor = await _user(db, "instructor")
    keeper = await _user(db, "storekeeper")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, instructor)
    kit = await _kit(db, wh)
    await _assign(db, client, session, kit, ops)

    r = await client.get(
        f"/inventory/sessions/{session.id}/equipment", headers=_headers(keeper)
    )
    assert r.status_code == 403
