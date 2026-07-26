"""E2E tests for the check-in scanner router (V2 R2-5): authentication is
required, the operations role-gate is enforced, and a successful scan
returns the student's name in the shape the door-scanner result card needs.

The service-layer rules themselves (unknown token -> 404, wrong cohort ->
409, not-covered-by-registration -> 409, already-recorded -> 409) are already
covered as mandatory unit tests in tests/services/sessions/test_registration.py
— this file re-proves them only at the HTTP boundary (status codes), it
doesn't re-litigate the logic; its real job is the ROUTER: auth, role-guard,
and response shape.

The `operations_user`/`operations_headers`/`other_role_user`/
`other_role_headers` fixtures, and the checkin router's test-session mount,
come from tests/routers/sessions/conftest.py (shared with
test_programs_cohorts.py / test_registration_desk.py — the R2-3 registration
desk tests already established this pattern for routers not yet wired into
app/routers/sessions/__init__.py).
"""

import uuid
from datetime import date

import httpx
import pytest
from sqlalchemy import select

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
from app.services.sessions.registration import register


async def _make_cohort_with_session(db, *, meeting_date=None) -> tuple[Cohort, Session]:
    program = Program(
        id=uuid.uuid4(), code=f"E2E-CHECKIN-{uuid.uuid4().hex[:8]}", name="E2E Checkin Workshop",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="E2E Checkin Cohort",
        status="registration_open", visibility="public",
        starts_on=date(2026, 8, 1),
    )
    db.add(cohort)
    await db.flush()
    session = Session(
        id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=meeting_date or date(2026, 8, 1),
    )
    db.add(session)
    await db.flush()
    return cohort, session


async def _make_registration(db, cohort: Cohort, *, name: str = "Test Student") -> Registration:
    contact = Contact(
        id=uuid.uuid4(), full_name=name, contact_roles=["student"],
        secondary_phones=[], preferred_language="ar", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    return await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="form")


async def _make_admin_user(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Admin", email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"), roles=["admin"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token(user.id, user.role_values)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


# ── auth / role gate ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_checkin_requires_authentication(db, client):
    cohort, session = await _make_cohort_with_session(db)
    registration = await _make_registration(db, cohort)

    resp = await client.post(
        "/sessions/checkin",
        json={"token": registration.ticket_token, "session_id": str(session.id)},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_checkin_rejects_non_operations_role(db, client, other_role_headers):
    cohort, session = await _make_cohort_with_session(db)
    registration = await _make_registration(db, cohort)

    resp = await client.post(
        "/sessions/checkin",
        json={"token": registration.ticket_token, "session_id": str(session.id)},
        headers=other_role_headers,
    )
    assert resp.status_code == 403


# ── successful scan ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_successful_checkin_returns_student_name_and_records_actor(
    db, client, operations_user, operations_headers
):
    cohort, session = await _make_cohort_with_session(db)
    registration = await _make_registration(db, cohort, name="Ada Lovelace")

    resp = await client.post(
        "/sessions/checkin",
        json={"token": registration.ticket_token, "session_id": str(session.id)},
        headers=operations_headers,
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["student_name"] == "Ada Lovelace"
    assert body["att_status"] == "present"
    assert body["method"] == "qr"
    assert body["cohort_name"] == cohort.name
    assert body["program_name"] == "E2E Checkin Workshop"

    record = (await db.execute(
        select(AttendanceRecord).where(AttendanceRecord.registration_id == registration.id)
    )).scalars().first()
    assert record is not None
    assert record.recorded_by_user_id == operations_user.id
    assert record.method == "qr"


@pytest.mark.asyncio
async def test_admin_role_also_allowed(db, client):
    """RequireRole lets admin through regardless of the specific allowed list."""
    cohort, session = await _make_cohort_with_session(db)
    registration = await _make_registration(db, cohort)
    admin = await _make_admin_user(db)

    resp = await client.post(
        "/sessions/checkin",
        json={"token": registration.ticket_token, "session_id": str(session.id)},
        headers=_auth_headers(admin),
    )
    assert resp.status_code == 200, resp.text


# ── error paths, re-proved at the HTTP boundary only ─────────────────────────

@pytest.mark.asyncio
async def test_checkin_unknown_token_returns_404(db, client, operations_headers):
    _, session = await _make_cohort_with_session(db)

    resp = await client.post(
        "/sessions/checkin",
        json={"token": "does-not-exist", "session_id": str(session.id)},
        headers=operations_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_checkin_wrong_cohort_returns_409(db, client, operations_headers):
    cohort_a, _ = await _make_cohort_with_session(db)
    _, session_b = await _make_cohort_with_session(db)
    registration = await _make_registration(db, cohort_a)

    resp = await client.post(
        "/sessions/checkin",
        json={"token": registration.ticket_token, "session_id": str(session_b.id)},
        headers=operations_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_checkin_already_recorded_returns_409(db, client, operations_headers):
    cohort, session = await _make_cohort_with_session(db)
    registration = await _make_registration(db, cohort)

    first = await client.post(
        "/sessions/checkin",
        json={"token": registration.ticket_token, "session_id": str(session.id)},
        headers=operations_headers,
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        "/sessions/checkin",
        json={"token": registration.ticket_token, "session_id": str(session.id)},
        headers=operations_headers,
    )
    assert second.status_code == 409


# ── today's sessions lookup ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_todays_sessions_requires_operations_role(db, client):
    resp = await client.get("/sessions/today")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_todays_sessions_lists_session_dated_today(db, client, operations_headers):
    today = date.today()
    cohort, session = await _make_cohort_with_session(db, meeting_date=today)
    _other_cohort, _other_session = await _make_cohort_with_session(db, meeting_date=date(2020, 1, 1))

    resp = await client.get("/sessions/today", headers=operations_headers)
    assert resp.status_code == 200, resp.text

    rows = resp.json()
    ids = [row["id"] for row in rows]
    assert str(session.id) in ids
    assert str(_other_session.id) not in ids

    row = next(r for r in rows if r["id"] == str(session.id))
    assert row["cohort_name"] == cohort.name
    assert row["program_name"] == "E2E Checkin Workshop"
