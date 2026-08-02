"""Cohort-level kit defaults over HTTP (Phase 3 follow-up to I2-1/I2-2).

Covers the three new `/inventory/cohorts/{cohort_id}/kits-defaults` endpoints
and the `GET /inventory/sessions/{session_id}/kits` view now resolving
through the cohort default when a session has no kit activity of its own.
"""

import uuid
from datetime import date

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.inventory import Kit, KitTemplate, Location, Warehouse
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User


async def _role_id(db, name: str = "Lead Facilitator"):
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


async def _cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"P-{uuid.uuid4().hex[:8]}", name="P",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="C", status="running")
    db.add(cohort)
    await db.flush()
    return cohort


async def _session(db, cohort: Cohort, lead: User | None = None) -> Session:
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today())
    db.add(session)
    await db.flush()
    if lead:
        db.add(SessionInstructor(
            id=uuid.uuid4(), session_id=session.id, user_id=lead.id, role_id=await _role_id(db)
        ))
        await db.flush()
    return session


# ── cohort default list CRUD ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_and_get_a_cohort_default_list(db, client):
    ops = await _user(db, "operations")
    cohort = await _cohort(db)
    loc = await _loc(db)
    wh = await _wh(db, loc)
    kit = await _kit(db, wh)
    await db.commit()

    ops_h = _headers(ops)
    put = await client.put(f"/inventory/cohorts/{cohort.id}/kits-defaults", headers=ops_h,
                           json={"kit_ids": [str(kit.id)]})
    assert put.status_code == 200, put.text
    assert [k["kit_id"] for k in put.json()["kits"]] == [str(kit.id)]

    got = await client.get(f"/inventory/cohorts/{cohort.id}/kits-defaults", headers=ops_h)
    assert got.status_code == 200
    assert got.json()["kits"][0]["label"] == kit.label


@pytest.mark.asyncio
async def test_get_defaults_on_a_missing_cohort_is_a_404(db, client):
    ops = await _user(db, "operations")
    await db.commit()
    resp = await client.get(f"/inventory/cohorts/{uuid.uuid4()}/kits-defaults", headers=_headers(ops))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_remove_a_cohort_default_kit(db, client):
    ops = await _user(db, "operations")
    cohort = await _cohort(db)
    loc = await _loc(db)
    wh = await _wh(db, loc)
    kit = await _kit(db, wh)
    await db.commit()

    ops_h = _headers(ops)
    await client.put(f"/inventory/cohorts/{cohort.id}/kits-defaults", headers=ops_h,
                     json={"kit_ids": [str(kit.id)]})
    removed = await client.delete(
        f"/inventory/cohorts/{cohort.id}/kits-defaults/{kit.id}", headers=ops_h
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["kits"] == []


# ── a session inheriting, then materializing, the cohort default ──────────

@pytest.mark.asyncio
async def test_a_fresh_session_view_shows_the_inherited_cohort_default(db, client):
    ops = await _user(db, "operations")
    lead = await _user(db, "instructor")
    cohort = await _cohort(db)
    loc = await _loc(db)
    wh = await _wh(db, loc)
    kit = await _kit(db, wh)
    session = await _session(db, cohort, lead=lead)
    await db.commit()

    ops_h = _headers(ops)
    await client.put(f"/inventory/cohorts/{cohort.id}/kits-defaults", headers=ops_h,
                     json={"kit_ids": [str(kit.id)]})

    view = await client.get(f"/inventory/sessions/{session.id}/kits", headers=_headers(lead))
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["level"] == "cohort"
    assert len(body["kits"]) == 1
    assert body["kits"][0]["kit_id"] == str(kit.id)
    assert body["kits"][0]["inherited"] is True


@pytest.mark.asyncio
async def test_assigning_a_kit_materializes_the_view_to_session_level(db, client):
    ops = await _user(db, "operations")
    lead = await _user(db, "instructor")
    cohort = await _cohort(db)
    loc = await _loc(db)
    wh = await _wh(db, loc)
    default_kit = await _kit(db, wh)
    extra_kit = await _kit(db, wh)
    session = await _session(db, cohort, lead=lead)
    await db.commit()

    ops_h = _headers(ops)
    await client.put(f"/inventory/cohorts/{cohort.id}/kits-defaults", headers=ops_h,
                     json={"kit_ids": [str(default_kit.id)]})

    assign = await client.put(f"/inventory/sessions/{session.id}/kits", headers=ops_h,
                              json={"kit_ids": [str(extra_kit.id)]})
    assert assign.status_code == 200, assign.text
    body = assign.json()
    assert body["level"] == "session"
    kit_ids = {k["kit_id"] for k in body["kits"]}
    assert kit_ids == {str(default_kit.id), str(extra_kit.id)}
    assert all(not k["inherited"] for k in body["kits"])

    # A later read confirms it stuck.
    view = await client.get(f"/inventory/sessions/{session.id}/kits", headers=_headers(lead))
    assert view.json()["level"] == "session"


@pytest.mark.asyncio
async def test_removing_the_last_inherited_kit_leaves_an_empty_session_level_list(db, client):
    ops = await _user(db, "operations")
    lead = await _user(db, "instructor")
    cohort = await _cohort(db)
    loc = await _loc(db)
    wh = await _wh(db, loc)
    kit = await _kit(db, wh)
    session = await _session(db, cohort, lead=lead)
    await db.commit()

    ops_h = _headers(ops)
    await client.put(f"/inventory/cohorts/{cohort.id}/kits-defaults", headers=ops_h,
                     json={"kit_ids": [str(kit.id)]})

    removed = await client.delete(
        f"/inventory/sessions/{session.id}/kits/{kit.id}", headers=ops_h
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["level"] == "session"
    assert removed.json()["kits"] == []

    # Reading it again must not silently revert to inheriting.
    view = await client.get(f"/inventory/sessions/{session.id}/kits", headers=_headers(lead))
    body = view.json()
    assert body["level"] == "session"
    assert body["kits"] == []


@pytest.mark.asyncio
async def test_changing_the_cohort_default_after_materialization_does_not_leak_in(db, client):
    ops = await _user(db, "operations")
    lead = await _user(db, "instructor")
    cohort = await _cohort(db)
    loc = await _loc(db)
    wh = await _wh(db, loc)
    original_kit = await _kit(db, wh)
    new_kit = await _kit(db, wh)
    session = await _session(db, cohort, lead=lead)
    await db.commit()

    ops_h = _headers(ops)
    await client.put(f"/inventory/cohorts/{cohort.id}/kits-defaults", headers=ops_h,
                     json={"kit_ids": [str(original_kit.id)]})

    # First touch on the session materializes the original default.
    await client.put(f"/inventory/sessions/{session.id}/kits", headers=ops_h,
                     json={"kit_ids": [str(original_kit.id)]})

    # The cohort default changes afterward.
    await client.put(f"/inventory/cohorts/{cohort.id}/kits-defaults", headers=ops_h,
                     json={"kit_ids": [str(new_kit.id)]})

    view = await client.get(f"/inventory/sessions/{session.id}/kits", headers=_headers(lead))
    body = view.json()
    assert body["level"] == "session"
    assert [k["kit_id"] for k in body["kits"]] == [str(original_kit.id)]


@pytest.mark.asyncio
async def test_a_session_with_no_kit_activity_and_no_cohort_default_is_level_none(db, client):
    lead = await _user(db, "instructor")
    cohort = await _cohort(db)
    session = await _session(db, cohort, lead=lead)
    await db.commit()

    view = await client.get(f"/inventory/sessions/{session.id}/kits", headers=_headers(lead))
    body = view.json()
    assert body["level"] == "none"
    assert body["kits"] == []
    assert body["can_finish"] is True
