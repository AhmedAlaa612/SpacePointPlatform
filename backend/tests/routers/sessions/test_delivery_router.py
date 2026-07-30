"""Endpoint tests for instructor session delivery (V2 W5 S5-1): role guards
(unassigned instructor -> 404, wrong role -> 403, ops always allowed),
response shape, and the cohort-complete endpoint. Redis-free — none of these
endpoints touch ARQ.
"""

import uuid
from datetime import date

import httpx
import pytest
from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.services.sessions.registration import register
from app.models.spine.contact import Contact


async def _role_id(db, name: str = "Lead Facilitator"):
    """I5-3: roles are rows now. The three are seeded by migration
    `c2a7b49e0022`, so tests look them up rather than inventing their own."""
    from sqlalchemy import select

    from app.models.sessions.delivery_role import DeliveryRole

    return await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))



@pytest.fixture
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_cohort_with_session(db, **overrides) -> tuple[Cohort, Session]:
    program = Program(
        id=uuid.uuid4(), code=f"DELIVR-{uuid.uuid4().hex[:8]}", name="Delivery Router Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Delivery Router Test Cohort",
        status="registration_open", visibility="public",
    )
    db.add(cohort)
    await db.flush()
    defaults = dict(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 20))
    defaults.update(overrides)
    session = Session(**defaults)
    db.add(session)
    await db.flush()
    return cohort, session


async def _make_registration(db, cohort: Cohort, *, name: str = "Router Test Student"):
    contact = Contact(
        id=uuid.uuid4(), full_name=name, contact_roles=["student"],
        secondary_phones=[], preferred_language="ar", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    return await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="form")


async def _assign(db, session: Session, user_id):
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=user_id, role_id=await _role_id(db)))
    await db.flush()


# ── role / assignment guards ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delivery_requires_authentication(db, client):
    _, session = await _make_cohort_with_session(db)
    resp = await client.get(f"/sessions/{session.id}/delivery")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delivery_rejects_wrong_role(db, client, other_role_headers):
    _, session = await _make_cohort_with_session(db)
    resp = await client.get(f"/sessions/{session.id}/delivery", headers=other_role_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delivery_404_for_unassigned_instructor(db, client, instructor_headers):
    _, session = await _make_cohort_with_session(db)
    resp = await client.get(f"/sessions/{session.id}/delivery", headers=instructor_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delivery_allowed_for_assigned_instructor(db, client, instructor_headers, instructor_user):
    _, session = await _make_cohort_with_session(db)
    await _assign(db, session, instructor_user.id)
    resp = await client.get(f"/sessions/{session.id}/delivery", headers=instructor_headers)
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_delivery_allowed_for_ops_without_assignment(db, client, operations_headers):
    _, session = await _make_cohort_with_session(db)
    resp = await client.get(f"/sessions/{session.id}/delivery", headers=operations_headers)
    assert resp.status_code == 200, resp.text


# ── roster + response shape ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delivery_returns_roster_with_program_and_cohort_names(db, client, operations_headers):
    cohort, session = await _make_cohort_with_session(db)
    await _make_registration(db, cohort, name="Roster Kid")

    resp = await client.get(f"/sessions/{session.id}/delivery", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cohort_name"] == cohort.name
    assert body["program_name"] == "Delivery Router Test Program"
    assert len(body["roster"]) == 1
    assert body["roster"][0]["student_name"] == "Roster Kid"
    assert body["roster"][0]["att_status"] is None


# ── start / mark done ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_session_sets_timestamp(db, client, operations_headers):
    _, session = await _make_cohort_with_session(db)
    resp = await client.post(f"/sessions/{session.id}/delivery/start", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["started_at"] is not None


@pytest.mark.asyncio
async def test_mark_done_sets_timestamp(db, client, operations_headers):
    _, session = await _make_cohort_with_session(db)
    resp = await client.post(f"/sessions/{session.id}/delivery/done", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["completed_at"] is not None


# ── manual attendance ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_attendance_writes_record(db, client, operations_headers):
    cohort, session = await _make_cohort_with_session(db)
    reg = await _make_registration(db, cohort, name="Attend Kid")

    resp = await client.put(
        f"/sessions/{session.id}/delivery/attendance/{reg.id}",
        json={"att_status": "present"}, headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["att_status"] == "present"
    assert body["method"] == "manual"
    assert body["student_name"] == "Attend Kid"

    record = (await db.execute(
        select(AttendanceRecord).where(AttendanceRecord.registration_id == reg.id)
    )).scalars().first()
    assert record is not None and record.att_status == "present"


@pytest.mark.asyncio
async def test_mark_attendance_requires_assignment_for_instructor(db, client, instructor_headers):
    cohort, session = await _make_cohort_with_session(db)
    reg = await _make_registration(db, cohort)

    resp = await client.put(
        f"/sessions/{session.id}/delivery/attendance/{reg.id}",
        json={"att_status": "present"}, headers=instructor_headers,
    )
    assert resp.status_code == 404


# ── QR scan ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scan_attendance_via_delivery_endpoint(db, client, operations_headers):
    cohort, session = await _make_cohort_with_session(db)
    reg = await _make_registration(db, cohort, name="Scan Kid")

    resp = await client.post(
        f"/sessions/{session.id}/delivery/scan", json={"token": reg.ticket_token}, headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["method"] == "qr"
    assert body["student_name"] == "Scan Kid"


# ── complete_cohort ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_complete_cohort_requires_operations(db, client, instructor_headers):
    cohort, _ = await _make_cohort_with_session(db)
    resp = await client.post(f"/sessions/cohorts/{cohort.id}/complete", headers=instructor_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_complete_cohort_sets_status(db, client, operations_headers):
    cohort, _ = await _make_cohort_with_session(db)
    resp = await client.post(f"/sessions/cohorts/{cohort.id}/complete", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    # Wrapped in {cohort, warnings} since S5-2 added the zero-reports warning
    # (tests/routers/sessions/test_reports_router.py covers the warning itself).
    assert resp.json()["cohort"]["status"] == "completed"
