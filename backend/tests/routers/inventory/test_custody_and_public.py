"""Session kit receipts, merch and the public scan page over HTTP
(I2-3/I2-4/I2-6).

Redis-free — the reminder job (I2-5) is the only part of this phase that
touches the queue, and it's tested separately against its own session.
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


# ── receiving, returning, and ops confirming — end to end ───────────────────

@pytest.mark.asyncio
async def test_the_whole_report_round_trip(db, client):
    ops = await _user(db, "operations")
    lead = await _user(db, "instructor")
    dubai, main = await _loc(db), await _loc(db, name="Main")
    dubai_wh, main_wh = await _wh(db, dubai), await _wh(db, main)
    session = await _session(db, lead)
    kit = await _kit(db, dubai_wh)
    await db.commit()

    ops_h, lead_h = _headers(ops), _headers(lead)

    # ops assigns — no separate hand-out step
    await client.put(f"/inventory/sessions/{session.id}/kits", headers=ops_h,
                     json={"kit_ids": [str(kit.id)]})

    # the instructor confirms they have it
    received = await client.post(f"/inventory/sessions/{session.id}/kits/receive", headers=lead_h,
                                 json={"kit_ids": [str(kit.id)]})
    assert received.status_code == 200, received.text
    assert received.json()["kits"][0]["received"] is True

    # and later reports it back — no location to pick
    back = await client.post(f"/inventory/sessions/{session.id}/kits/mark-returned", headers=lead_h,
                             json={"kit_ids": [str(kit.id)]})
    assert back.status_code == 200
    assert back.json()["kits"][0]["return_status"] == "returned"
    detail = (await client.get(f"/inventory/kits/{kit.id}", headers=ops_h)).json()
    assert detail["location_name"] == "Dubai", "a report doesn't move the kit"

    # ops reviews it and restocks to Main
    confirmed = await client.post(f"/inventory/sessions/{session.id}/kits/confirm-returns", headers=ops_h,
                                  json={"kit_ids": [str(kit.id)], "restock_warehouse_id": str(main_wh.id)})
    assert confirmed.status_code == 200
    assert confirmed.json()["kits"][0]["ops_confirmed"] is True
    detail = (await client.get(f"/inventory/kits/{kit.id}", headers=ops_h)).json()
    assert detail["location_name"] == "Main"


@pytest.mark.asyncio
async def test_confirming_without_a_report_is_a_409(db, client):
    ops = await _user(db, "operations")
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead)
    kit = await _kit(db, wh)
    await db.commit()

    await client.put(f"/inventory/sessions/{session.id}/kits", headers=_headers(ops),
                     json={"kit_ids": [str(kit.id)]})
    resp = await client.post(f"/inventory/sessions/{session.id}/kits/confirm-returns",
                             headers=_headers(ops), json={"kit_ids": [str(kit.id)]})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_an_unrelated_instructor_cannot_receive_or_return(db, client):
    """404, not 403 — don't leak that the session exists."""
    ops = await _user(db, "operations")
    lead = await _user(db, "instructor")
    outsider = await _user(db, "instructor")
    session = await _session(db, lead)
    kit = await _kit(db, await _wh(db, await _loc(db)))
    await db.commit()
    await client.put(f"/inventory/sessions/{session.id}/kits", headers=_headers(ops),
                     json={"kit_ids": [str(kit.id)]})

    h = _headers(outsider)
    assert (await client.post(f"/inventory/sessions/{session.id}/kits/receive", headers=h,
                              json={"kit_ids": [str(kit.id)]})).status_code == 404
    assert (await client.post(f"/inventory/sessions/{session.id}/kits/mark-returned", headers=h,
                              json={"kit_ids": [str(kit.id)]})).status_code == 404


@pytest.mark.asyncio
async def test_the_session_kit_view_mirrors_the_finish_gate(db, client):
    """`can_finish` has to match what mark_done enforces, so the UI can grey
    the button out instead of letting someone press it and get a 409."""
    ops = await _user(db, "operations")
    lead = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    session = await _session(db, lead)
    kit = await _kit(db, wh)
    await db.commit()

    await client.put(f"/inventory/sessions/{session.id}/kits", headers=_headers(ops),
                     json={"kit_ids": [str(kit.id)]})

    view = (await client.get(f"/inventory/sessions/{session.id}/kits", headers=_headers(lead))).json()
    assert view["can_finish"] is False
    assert view["outstanding_post_checks"] == [str(kit.id)]
    assert view["kits"][0]["post_checked"] is False


# ── merchandise ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_issuing_and_returning_a_vest(db, client):
    ops = await _user(db, "operations")
    person = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    vest = Item(id=uuid.uuid4(), name="Vest (L)", category="merch", returnable_default=True)
    db.add(vest)
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=vest.id, warehouse_id=wh.id, qty=4))
    await db.commit()

    ops_h = _headers(ops)
    issued = await client.post("/inventory/merch/issue", headers=ops_h, json={
        "item_id": str(vest.id), "to_user_id": str(person.id),
        "from_warehouse_id": str(wh.id), "due_back_on": "2026-12-31",
    })
    assert issued.status_code == 201, issued.text
    assert issued.json()["due_back_on"] == "2026-12-31"

    held = (await client.get(f"/inventory/merch/held/{person.id}", headers=ops_h)).json()
    assert held == [{"item_id": str(vest.id), "item_name": "Vest (L)",
                     "variant_group": None, "variant_label": None,
                     "qty": 1, "due_back_on": "2026-12-31"}]

    mine = (await client.get("/inventory/my-merch", headers=_headers(person))).json()
    assert mine[0]["item_name"] == "Vest (L)"

    await client.post("/inventory/merch/return", headers=ops_h, json={
        "item_id": str(vest.id), "from_user_id": str(person.id), "to_warehouse_id": str(wh.id),
    })
    assert (await client.get(f"/inventory/merch/held/{person.id}", headers=ops_h)).json() == []


@pytest.mark.asyncio
async def test_a_tshirt_gets_no_due_date_even_if_one_is_sent(db, client):
    ops = await _user(db, "operations")
    person = await _user(db, "instructor")
    loc = await _loc(db)
    wh = await _wh(db, loc)
    shirt = Item(id=uuid.uuid4(), name="T-Shirt (M)", category="merch", returnable_default=False)
    db.add(shirt)
    await db.flush()
    db.add(StockLevel(id=uuid.uuid4(), item_id=shirt.id, warehouse_id=wh.id, qty=4))
    await db.commit()

    issued = await client.post("/inventory/merch/issue", headers=_headers(ops), json={
        "item_id": str(shirt.id), "to_user_id": str(person.id),
        "from_warehouse_id": str(wh.id), "due_back_on": "2026-12-31",
    })
    assert issued.json()["due_back_on"] is None
    assert (await client.get("/inventory/overdue", headers=_headers(ops))).json() == []


# ── the public scan page ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scanning_a_kit_needs_no_login(db, client):
    loc = await _loc(db)
    wh = await _wh(db, loc)
    kit = await _kit(db, wh)
    await db.commit()

    resp = await client.get(f"/public/kit/{kit.public_token}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["label"] == kit.label
    assert body["owner"] == "SpacePoint"


@pytest.mark.asyncio
async def test_a_scan_reveals_nothing_about_where_it_is_or_who_has_it(db, client):
    """A QR on a box that leaves the building is readable by whoever picks it
    up. It must not tell them which warehouse to visit or who to follow."""
    ops = await _user(db, "operations")
    holder = await _user(db, "instructor")
    loc = await _loc(db, name="Main Warehouse")
    wh = await _wh(db, loc)
    kit = await _kit(db, wh)
    kit.current_holder_user_id = holder.id
    await db.commit()

    body = (await client.get(f"/public/kit/{kit.public_token}")).json()
    serialised = str(body)
    assert "Main Warehouse" not in serialised
    assert holder.full_name not in serialised
    assert "contents" not in body and "location_name" not in body


@pytest.mark.asyncio
async def test_an_unknown_token_is_a_404_not_a_hint(db, client):
    assert (await client.get(f"/public/kit/{uuid.uuid4().hex}")).status_code == 404


@pytest.mark.asyncio
async def test_the_qr_renders_on_demand(db, client):
    loc = await _loc(db)
    wh = await _wh(db, loc)
    kit = await _kit(db, wh)
    await db.commit()

    resp = await client.get(f"/public/kit/{kit.public_token}/qr.png")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_the_token_is_not_derived_from_the_label(db, client):
    """Guessing a code from what's printed next to it is the mistake the
    ticket tokens were designed to avoid."""
    loc = await _loc(db)
    wh = await _wh(db, loc)
    kit = await _kit(db, wh)
    await db.commit()
    assert kit.label not in kit.public_token
    assert len(kit.public_token) == 64
