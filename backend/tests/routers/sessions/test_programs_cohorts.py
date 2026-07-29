"""Tests for the registration-desk's Programs/Cohorts CRUD + session
generation + per-session instructor assignment (V2 R2-3). Follows
test_public_registration.py's pattern: a real httpx.AsyncClient against the
actual app, with get_db/get_arq_redis dependency-overridden onto this test's
own db/arq_redis fixtures.
"""

import uuid
from datetime import date, time

import httpx
import pytest
from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User
from app.workers.settings import get_arq_redis


# `client` (Redis-free) and `arq_client` (real ARQ pool) live in
# tests/conftest.py. The local copy that used to be here bound *every* test in
# this file to a live Redis, including ones that never enqueue anything (I0-1b).


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
        status="planned", visibility="public",
    )
    defaults.update(overrides)
    cohort = Cohort(**defaults)
    db.add(cohort)
    await db.flush()
    return cohort


# ── Programs ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_program(db, client, operations_headers):
    resp = await client.post(
        "/sessions/programs",
        json={
            "code": "SATKIT-WS-2026-Q3",
            "name": "CubeSat Workshop",
            "program_type": "workshop",
            "pricing_model": "paid",
            "price": "250.00",
            "default_capacity": 20,
        },
        headers=operations_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == "SATKIT-WS-2026-Q3"
    assert body["active"] is True

    program = (await db.execute(select(Program).where(Program.code == "SATKIT-WS-2026-Q3"))).scalars().first()
    assert program is not None
    assert program.name == "CubeSat Workshop"


@pytest.mark.asyncio
async def test_create_program_duplicate_code_conflicts(db, client, operations_headers):
    await _make_program(db, code="DUP-CODE-1")

    resp = await client.post(
        "/sessions/programs",
        json={"code": "DUP-CODE-1", "name": "Another", "program_type": "course", "pricing_model": "free"},
        headers=operations_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_and_get_and_update_program(db, client, operations_headers):
    program = await _make_program(db, name="Original Name")

    list_resp = await client.get("/sessions/programs", headers=operations_headers)
    assert list_resp.status_code == 200
    assert any(p["id"] == str(program.id) for p in list_resp.json())

    get_resp = await client.get(f"/sessions/programs/{program.id}", headers=operations_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Original Name"

    patch_resp = await client.patch(
        f"/sessions/programs/{program.id}", json={"name": "Renamed Program", "active": False},
        headers=operations_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Renamed Program"
    assert patch_resp.json()["active"] is False

    missing_resp = await client.get(f"/sessions/programs/{uuid.uuid4()}", headers=operations_headers)
    assert missing_resp.status_code == 404


@pytest.mark.asyncio
async def test_programs_require_operations_role(db, client, other_role_headers):
    resp = await client.get("/sessions/programs", headers=other_role_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_programs_require_auth_at_all(db, client):
    resp = await client.get("/sessions/programs")
    assert resp.status_code == 401


# ── Cohorts ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_cohort(db, client, operations_headers):
    program = await _make_program(db)

    resp = await client.post(
        "/sessions/cohorts",
        json={
            "program_id": str(program.id),
            "name": "Q3 Cohort A",
            "starts_on": "2026-08-03",
            "ends_on": "2026-08-24",
            "capacity": 15,
        },
        headers=operations_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Q3 Cohort A"
    assert body["status"] == "planned"
    assert body["program_id"] == str(program.id)


@pytest.mark.asyncio
async def test_create_cohort_missing_program_404(db, client, operations_headers):
    resp = await client.post(
        "/sessions/cohorts",
        json={"program_id": str(uuid.uuid4()), "name": "Orphan Cohort"},
        headers=operations_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_cohorts_filterable_by_program(db, client, operations_headers):
    program_a = await _make_program(db, code="PROG-A")
    program_b = await _make_program(db, code="PROG-B")
    cohort_a = await _make_cohort(db, program_a, name="Cohort A1")
    await _make_cohort(db, program_b, name="Cohort B1")

    resp = await client.get("/sessions/cohorts", params={"program_id": str(program_a.id)}, headers=operations_headers)
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert names == ["Cohort A1"]
    assert resp.json()[0]["program_code"] == "PROG-A"
    assert str(cohort_a.id) == resp.json()[0]["id"]


@pytest.mark.asyncio
async def test_update_cohort_opens_registration(db, client, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program, status="planned")

    resp = await client.patch(
        f"/sessions/cohorts/{cohort.id}", json={"status": "registration_open"}, headers=operations_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "registration_open"

    await db.refresh(cohort)
    assert cohort.status == "registration_open"


# ── Session generation ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_sessions_creates_weekly_rows(db, client, operations_headers):
    program = await _make_program(db)
    # 2026-08-03 is a Monday.
    cohort = await _make_cohort(db, program, starts_on=date(2026, 8, 3))

    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/sessions:generate",
        json={"weekdays": [0], "count": 4, "starts_at": "10:00:00"},
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["skipped"] == 0
    assert len(body["created"]) == 4
    dates = [s["meeting_date"] for s in body["created"]]
    assert dates == ["2026-08-03", "2026-08-10", "2026-08-17", "2026-08-24"]
    assert all(s["starts_at"] == "10:00:00" for s in body["created"])

    rows = (await db.execute(select(Session).where(Session.cohort_id == cohort.id))).scalars().all()
    assert len(rows) == 4


@pytest.mark.asyncio
async def test_generate_sessions_supports_multiple_weekdays(db, client, operations_headers):
    program = await _make_program(db)
    # 2026-08-03 is a Monday.
    cohort = await _make_cohort(db, program, starts_on=date(2026, 8, 3))

    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/sessions:generate",
        json={"weekdays": [0, 2], "count": 2, "starts_at": None},  # Monday + Wednesday, 2 weeks
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["skipped"] == 0
    dates = sorted(s["meeting_date"] for s in body["created"])
    assert dates == ["2026-08-03", "2026-08-05", "2026-08-10", "2026-08-12"]


@pytest.mark.asyncio
async def test_generate_sessions_skips_existing_slot(db, client, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program, starts_on=date(2026, 9, 7))  # a Monday

    existing = Session(
        id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 7), starts_at=time(9, 0),
    )
    db.add(existing)
    await db.flush()

    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/sessions:generate",
        json={"weekdays": [0], "count": 3, "starts_at": "09:00:00"},
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["skipped"] == 1
    assert len(body["created"]) == 2

    rows = (await db.execute(select(Session).where(Session.cohort_id == cohort.id))).scalars().all()
    assert len(rows) == 3  # the pre-existing one + the 2 newly created


@pytest.mark.asyncio
async def test_generate_sessions_picks_first_matching_weekday_on_or_after_start(db, client, operations_headers):
    program = await _make_program(db)
    # 2026-08-05 is a Wednesday; asking for weekday=5 (Saturday) should land
    # on the following Saturday, 2026-08-08, not on starts_on itself.
    cohort = await _make_cohort(db, program, starts_on=date(2026, 8, 5))

    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/sessions:generate",
        json={"weekdays": [5], "count": 1, "starts_at": None},
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["created"][0]["meeting_date"] == "2026-08-08"


@pytest.mark.asyncio
async def test_generate_sessions_requires_cohort_start_date(db, client, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program, starts_on=None)

    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/sessions:generate",
        json={"weekdays": [0], "count": 2},
        headers=operations_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_sessions_returns_them_ordered_by_date(db, client, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program, starts_on=date(2026, 8, 3))
    db.add_all([
        Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 10)),
        Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 3)),
    ])
    await db.flush()

    resp = await client.get(f"/sessions/cohorts/{cohort.id}/sessions", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    dates = [s["meeting_date"] for s in resp.json()]
    assert dates == ["2026-08-03", "2026-08-10"]


@pytest.mark.asyncio
async def test_add_single_session_creates_a_one_off_date(db, client, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program, starts_on=date(2026, 8, 3))

    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/sessions",
        json={"meeting_date": "2026-08-15", "starts_at": "14:00:00", "title": "Make-up session", "price": "50.00"},
        headers=operations_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["meeting_date"] == "2026-08-15"
    assert body["title"] == "Make-up session"
    assert body["price"] == "50.00"

    rows = (await db.execute(select(Session).where(Session.cohort_id == cohort.id))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_add_single_session_conflict_on_duplicate_slot(db, client, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program, starts_on=date(2026, 8, 3))
    db.add(Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 15), starts_at=time(14, 0)))
    await db.flush()

    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/sessions",
        json={"meeting_date": "2026-08-15", "starts_at": "14:00:00"},
        headers=operations_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_update_session_edits_title_and_price(db, client, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program, starts_on=date(2026, 8, 3))
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 3))
    db.add(session)
    await db.flush()

    resp = await client.patch(
        f"/sessions/cohorts/{cohort.id}/sessions/{session.id}",
        json={"title": "Intro to Orbits", "price": "75.00"},
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "Intro to Orbits"
    assert body["price"] == "75.00"


# ── Per-session instructor assignment ───────────────────────────────────────

async def _make_instructor_user(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Test Instructor", email=f"instructor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["instructor"],
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_assign_instructor_to_session(db, client, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program, starts_on=date(2026, 8, 3))
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 3))
    db.add(session)
    await db.flush()
    instructor = await _make_instructor_user(db)

    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/sessions/{session.id}/instructors",
        json={"user_id": str(instructor.id), "role": "lead"},
        headers=operations_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["full_name"] == "Test Instructor"

    list_resp = await client.get(f"/sessions/cohorts/{cohort.id}/sessions", headers=operations_headers)
    session_out = next(s for s in list_resp.json() if s["id"] == str(session.id))
    assert len(session_out["instructors"]) == 1
    assert session_out["instructors"][0]["user_id"] == str(instructor.id)


@pytest.mark.asyncio
async def test_unassign_instructor_from_session(db, client, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program, starts_on=date(2026, 8, 3))
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 3))
    db.add(session)
    await db.flush()
    instructor = await _make_instructor_user(db)

    await client.post(
        f"/sessions/cohorts/{cohort.id}/sessions/{session.id}/instructors",
        json={"user_id": str(instructor.id)},
        headers=operations_headers,
    )
    resp = await client.delete(
        f"/sessions/cohorts/{cohort.id}/sessions/{session.id}/instructors/{instructor.id}",
        headers=operations_headers,
    )
    assert resp.status_code == 204

    list_resp = await client.get(f"/sessions/cohorts/{cohort.id}/sessions", headers=operations_headers)
    session_out = next(s for s in list_resp.json() if s["id"] == str(session.id))
    assert session_out["instructors"] == []
