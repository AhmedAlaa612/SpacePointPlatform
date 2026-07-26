"""Tests for GET /sessions/dashboard (V2 S6-2)."""

import uuid
from datetime import date, datetime, timezone, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.dependencies import get_current_active_user
from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session
from app.models.spine.contact import Contact
from app.models.user import User


async def _persist_user(db, roles: list[str]) -> tuple[User, dict]:
    user = User(
        id=uuid.uuid4(), full_name=f"{roles[0].title()} User",
        email=f"{roles[0]}-{uuid.uuid4().hex[:8]}@example.com",
        roles=roles, status="active",
        password_hash=get_password_hash("password123"),
    )
    db.add(user)
    await db.flush()
    token = create_access_token(user.id, roles)
    return user, {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def ops_user(db) -> User:
    user, _ = await _persist_user(db, ["operations"])
    return user


@pytest_asyncio.fixture
async def ops_headers(db, ops_user) -> dict:
    _, headers = await _persist_user(db, ["operations"])
    return headers


@pytest_asyncio.fixture
async def admin_headers(db) -> dict:
    _, headers = await _persist_user(db, ["admin"])
    return headers


@pytest_asyncio.fixture
async def intern_headers(db) -> dict:
    _, headers = await _persist_user(db, ["intern"])
    return headers


async def _make_program(db, **overrides) -> Program:
    defaults = dict(
        id=uuid.uuid4(), code=f"PROG-{uuid.uuid4().hex[:8]}", name="Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    defaults.update(overrides)
    p = Program(**defaults)
    db.add(p)
    await db.flush()
    return p


async def _make_cohort(db, program: Program, **overrides) -> Cohort:
    defaults = dict(
        id=uuid.uuid4(), program_id=program.id, name="Test Cohort",
        status="planned", visibility="public",
    )
    defaults.update(overrides)
    c = Cohort(**defaults)
    db.add(c)
    await db.flush()
    return c


async def _make_session(db, cohort: Cohort, **overrides) -> Session:
    defaults = dict(
        id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today(),
    )
    defaults.update(overrides)
    s = Session(**defaults)
    db.add(s)
    await db.flush()
    return s


async def _make_contact(db, **overrides) -> Contact:
    defaults = dict(
        id=uuid.uuid4(), full_name="Test Student", contact_roles=["student"],
    )
    defaults.update(overrides)
    c = Contact(**defaults)
    db.add(c)
    await db.flush()
    return c


async def _make_registration(db, *, contact: Contact, cohort: Cohort, **overrides) -> Registration:
    defaults = dict(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id,
        ticket_token=f"tok-{uuid.uuid4().hex}", registered_via="form",
        status="registered",
    )
    defaults.update(overrides)
    r = Registration(**defaults)
    db.add(r)
    await db.flush()
    return r


@pytest.mark.asyncio
async def test_dashboard_returns_zeroes_with_no_data(db, client, ops_headers):
    resp = await client.get("/sessions/dashboard", headers=ops_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["students_trained"] == 0
    assert data["active_cohorts"] == 0
    assert data["upcoming_meetings_7d"] == 0
    assert data["attendance_rate_30d"] == 0.0
    assert data["unpaid_count"] == 0
    assert data["unpaid_sum"] == "0"
    assert data["registrations_7d"] == 0
    assert data["open_calls_pending"] == 0


@pytest.mark.asyncio
async def test_dashboard_counts_students_trained(db, client, ops_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program, status="completed")
    contact = await _make_contact(db)
    await _make_registration(db, contact=contact, cohort=cohort, status="registered")

    resp = await client.get("/sessions/dashboard", headers=ops_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["students_trained"] == 1


@pytest.mark.asyncio
async def test_dashboard_counts_active_cohorts(db, client, ops_headers):
    program = await _make_program(db)
    await _make_cohort(db, program, status="running")

    resp = await client.get("/sessions/dashboard", headers=ops_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["active_cohorts"] == 1


@pytest.mark.asyncio
async def test_dashboard_counts_upcoming_meetings(db, client, ops_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    await _make_session(db, cohort, meeting_date=date.today() + timedelta(days=1))
    await _make_session(db, cohort, meeting_date=date.today() + timedelta(days=10))

    resp = await client.get("/sessions/dashboard", headers=ops_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["upcoming_meetings_7d"] == 1


@pytest.mark.asyncio
async def test_dashboard_computes_attendance_rate(db, client, ops_headers, ops_user):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    session = await _make_session(db, cohort)
    c1 = await _make_contact(db)
    c2 = await _make_contact(db)
    reg1 = await _make_registration(db, contact=c1, cohort=cohort)
    reg2 = await _make_registration(db, contact=c2, cohort=cohort)
    now = datetime.now(timezone.utc)
    db.add(AttendanceRecord(
        id=uuid.uuid4(), registration_id=reg1.id, session_id=session.id,
        att_status="present", method="manual", recorded_by_user_id=ops_user.id,
        recorded_at=now,
    ))
    db.add(AttendanceRecord(
        id=uuid.uuid4(), registration_id=reg2.id, session_id=session.id,
        att_status="absent", method="manual", recorded_by_user_id=ops_user.id,
        recorded_at=now,
    ))
    await db.flush()

    resp = await client.get("/sessions/dashboard", headers=ops_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["attendance_rate_30d"] == 0.5


@pytest.mark.asyncio
async def test_dashboard_counts_unpaid(db, client, ops_headers):
    program = await _make_program(db, pricing_model="paid")
    cohort = await _make_cohort(db, program)
    c1 = await _make_contact(db)
    c2 = await _make_contact(db)
    await _make_registration(db, contact=c1, cohort=cohort, payment_status="unpaid", price_charged="100.00")
    await _make_registration(db, contact=c2, cohort=cohort, payment_status="unpaid", price_charged="50.00")

    resp = await client.get("/sessions/dashboard", headers=ops_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["unpaid_count"] == 2
    assert data["unpaid_sum"] == "150.00"


@pytest.mark.asyncio
async def test_dashboard_counts_recent_registrations(db, client, ops_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    c1 = await _make_contact(db)
    c2 = await _make_contact(db)
    await _make_registration(db, contact=c1, cohort=cohort, created_at=datetime.now(timezone.utc) - timedelta(days=6))
    await _make_registration(db, contact=c2, cohort=cohort, created_at=datetime.now(timezone.utc) - timedelta(days=14))

    resp = await client.get("/sessions/dashboard", headers=ops_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["registrations_7d"] == 1


@pytest.mark.asyncio
async def test_dashboard_counts_open_calls(db, client, ops_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    await _make_session(db, cohort, staffing_status="open_call")
    await _make_session(db, cohort, staffing_status="staffed")
    await _make_session(db, cohort, staffing_status="unstaffed")

    resp = await client.get("/sessions/dashboard", headers=ops_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["open_calls_pending"] == 1


@pytest.mark.asyncio
async def test_dashboard_requires_operations_or_admin(db, client, intern_headers):
    resp = await client.get("/sessions/dashboard", headers=intern_headers)
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_dashboard_allows_admin(db, client, admin_headers):
    resp = await client.get("/sessions/dashboard", headers=admin_headers)
    assert resp.status_code == 200, resp.text
