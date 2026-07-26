"""Tests for GET /public/catalog (V2 R3-1). Deliberately uses a client
fixture that only overrides get_db, not get_arq_redis — this endpoint is a
plain read, no ARQ involved, and the ARQ-backed client fixture in
test_programs_cohorts.py needs a real Redis connection just to construct.
Keeping this file Redis-free means it (and the info_session regression test
below) can run without Docker/Redis running at all.
"""

import uuid
from datetime import date

import httpx
import pytest

from app.db.session import get_db
from app.main import app
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration


@pytest.fixture
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_program(db, **overrides) -> Program:
    defaults = dict(
        id=uuid.uuid4(), code=f"TEST-{uuid.uuid4().hex[:8]}", name="Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    defaults.update(overrides)
    program = Program(**defaults)
    db.add(program)
    await db.flush()
    return program


async def _make_cohort(db, program: Program, **overrides) -> Cohort:
    defaults = dict(
        id=uuid.uuid4(), program_id=program.id, name="Test Cohort",
        status="registration_open", visibility="public",
    )
    defaults.update(overrides)
    cohort = Cohort(**defaults)
    db.add(cohort)
    await db.flush()
    return cohort


async def _make_registration(db, cohort: Cohort, **overrides):
    from app.models.spine.contact import Contact

    contact = Contact(id=uuid.uuid4(), full_name="Catalog Test Student", contact_roles=["student"])
    db.add(contact)
    await db.flush()

    defaults = dict(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id,
        ticket_token=f"tok-{uuid.uuid4().hex}", registered_via="form", status="registered",
    )
    defaults.update(overrides)
    reg = Registration(**defaults)
    db.add(reg)
    await db.flush()
    return reg


@pytest.mark.asyncio
async def test_catalog_lists_open_public_cohort_with_program_fields(db, client):
    program = await _make_program(
        db, name="CubeSat Workshop", description="Build a cube satellite", pricing_model="paid", price="250.00",
    )
    cohort = await _make_cohort(
        db, program, starts_on=date(2026, 8, 10), ends_on=date(2026, 8, 12), location="SpacePoint HQ",
    )

    resp = await client.get("/public/catalog")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    match = next(i for i in items if i["cohort_id"] == str(cohort.id))
    assert match["program_name"] == "CubeSat Workshop"
    assert match["description"] == "Build a cube satellite"
    assert match["starts_on"] == "2026-08-10"
    assert match["location"] == "SpacePoint HQ"
    assert match["price_display"] == "AED 250.00"
    assert match["registration_endpoint"] == f"/public/register/{cohort.id}"


@pytest.mark.asyncio
async def test_catalog_excludes_non_open_and_private_cohorts(db, client):
    program = await _make_program(db)
    planned = await _make_cohort(db, program, name="Planned", status="planned")
    private = await _make_cohort(db, program, name="Private", visibility="private")
    open_public = await _make_cohort(db, program, name="Open Public")

    resp = await client.get("/public/catalog")
    ids = {i["cohort_id"] for i in resp.json()}
    assert str(planned.id) not in ids
    assert str(private.id) not in ids
    assert str(open_public.id) in ids


@pytest.mark.asyncio
async def test_catalog_free_program_price_display(db, client):
    program = await _make_program(db, pricing_model="free")
    cohort = await _make_cohort(db, program)

    resp = await client.get("/public/catalog")
    match = next(i for i in resp.json() if i["cohort_id"] == str(cohort.id))
    assert match["price_display"] == "Free"


@pytest.mark.asyncio
async def test_catalog_spots_left_and_limited_flag(db, client):
    program = await _make_program(db)
    # capacity 20, 19 active registrations -> 1 spot left, 5% -> limited.
    cohort = await _make_cohort(db, program, capacity=20)
    for _ in range(19):
        await _make_registration(db, cohort)

    resp = await client.get("/public/catalog")
    match = next(i for i in resp.json() if i["cohort_id"] == str(cohort.id))
    assert match["spots_left"] == 1
    assert match["is_limited"] is True


@pytest.mark.asyncio
async def test_catalog_not_limited_at_exactly_10_percent(db, client):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program, capacity=10)
    for _ in range(9):
        await _make_registration(db, cohort)

    resp = await client.get("/public/catalog")
    match = next(i for i in resp.json() if i["cohort_id"] == str(cohort.id))
    assert match["spots_left"] == 1
    assert match["is_limited"] is False


@pytest.mark.asyncio
async def test_catalog_uncapped_cohort_has_no_spots_left(db, client):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program, capacity=None)

    resp = await client.get("/public/catalog")
    match = next(i for i in resp.json() if i["cohort_id"] == str(cohort.id))
    assert match["spots_left"] is None
    assert match["is_limited"] is False


@pytest.mark.asyncio
async def test_catalog_cancelled_registrations_dont_count_against_capacity(db, client):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program, capacity=5)
    for _ in range(4):
        await _make_registration(db, cohort, status="cancelled")

    resp = await client.get("/public/catalog")
    match = next(i for i in resp.json() if i["cohort_id"] == str(cohort.id))
    assert match["spots_left"] == 5


# ── Regression: schemas/sessions/programs.py's ProgramType Literal used to
# say workshop|course|session even though the e5a2c93f0005 migration rewrote
# all program_type data from 'session' to 'info_session' — creating/reading
# a program with that type failed Pydantic validation. Not a catalog bug per
# se, but caught while building the catalog endpoint (which surfaces
# program_type) and fixed in the same pass. ──

@pytest.mark.asyncio
async def test_program_info_session_type_accepted_on_create_and_read(db, client, operations_headers):
    resp = await client.post(
        "/sessions/programs",
        json={
            "code": f"INFO-{uuid.uuid4().hex[:8]}", "name": "Info Session",
            "program_type": "info_session", "pricing_model": "free",
        },
        headers=operations_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["program_type"] == "info_session"

    get_resp = await client.get(f"/sessions/programs/{resp.json()['id']}", headers=operations_headers)
    assert get_resp.status_code == 200, get_resp.text
    assert get_resp.json()["program_type"] == "info_session"


@pytest.mark.asyncio
async def test_catalog_surfaces_info_session_program_type(db, client):
    program = await _make_program(db, program_type="info_session")
    cohort = await _make_cohort(db, program)

    resp = await client.get("/public/catalog")
    match = next(i for i in resp.json() if i["cohort_id"] == str(cohort.id))
    assert match["program_type"] == "info_session"


# ── Public ticket page (operator report 2026-07-26: emailed link 404'd) ──────

@pytest.mark.asyncio
async def test_public_ticket_returns_the_details_printed_on_the_ticket(db, client):
    """The emailed link and the QR both point at /t/{token}; that route had no
    backing endpoint, so every student clicking their ticket got a 404."""
    import uuid as _uuid

    from app.models.sessions.registration import Registration
    from app.models.spine.contact import Contact

    program = await _make_program(db, name="Rocketry 101")
    cohort = await _make_cohort(db, program, name="July Cohort", location="Dubai")
    contact = Contact(id=_uuid.uuid4(), full_name="Ticket Holder", email="holder@example.com")
    db.add(contact)
    await db.flush()
    registration = Registration(
        id=_uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id,
        ticket_token="tok_" + _uuid.uuid4().hex, registered_via="desk",
    )
    db.add(registration)
    await db.commit()

    resp = await client.get(f"/public/ticket/{registration.ticket_token}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["student_name"] == "Ticket Holder"
    assert body["program_name"] == "Rocketry 101"
    assert body["location"] == "Dubai"
    assert body["checked_in"] is False
    # No auth on this route, so it must not leak anything beyond the ticket.
    assert "student_email" not in body
    assert "contact_id" not in body


@pytest.mark.asyncio
async def test_public_ticket_unknown_token_is_404(db, client):
    resp = await client.get("/public/ticket/definitely-not-a-real-token")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_public_ticket_qr_renders_a_png(db, client):
    import uuid as _uuid

    from app.models.sessions.registration import Registration
    from app.models.spine.contact import Contact

    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    contact = Contact(id=_uuid.uuid4(), full_name="QR Holder", email="qr@example.com")
    db.add(contact)
    await db.flush()
    registration = Registration(
        id=_uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id,
        ticket_token="tok_" + _uuid.uuid4().hex, registered_via="desk",
    )
    db.add(registration)
    await db.commit()

    resp = await client.get(f"/public/ticket/{registration.ticket_token}/qr.png")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:8] == b"\x89PNG\r\n\x1a\n"
