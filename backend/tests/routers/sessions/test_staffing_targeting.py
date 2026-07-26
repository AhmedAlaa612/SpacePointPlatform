"""Router-level coverage for targeted open calls (operator, 2026-07-26).

Separate from test_staffing_router.py because that file's client fixture needs
a live Redis (one of its tests asserts on the ARQ queue). Nothing here enqueues
anything, so this uses a Redis-free client instead — routing and access control
shouldn't need a message broker to test.
"""

import uuid
from datetime import date

import httpx
import pytest

from app.db.session import get_db
from app.main import app
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User
from app.workers.settings import get_arq_redis


@pytest.fixture
async def client(db):
    async def _override_get_db():
        yield db

    async def _override_get_arq_redis():
        return None

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_arq_redis] = _override_get_arq_redis
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_session(db) -> Session:
    program = Program(
        id=uuid.uuid4(), code=f"TGT-{uuid.uuid4().hex[:8]}", name="Targeting Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Targeting Cohort",
        status="planned", visibility="public",
    )
    db.add(cohort)
    await db.flush()
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 1))
    db.add(session)
    await db.flush()
    return session


@pytest.mark.asyncio
async def test_open_call_with_user_ids_persists_them_as_the_gate(
    db, client, operations_headers, instructor_user: User,
):
    """The picker used to only filter notifications — the session stayed
    visible to every instructor. The chosen ids must now come back on the
    session as its restriction."""
    session = await _make_session(db)
    await db.commit()

    resp = await client.post(
        f"/sessions/{session.id}/staffing/open-call",
        json={"user_ids": [str(instructor_user.id)]},
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["staffing_status"] == "open_call"
    assert body["target_user_ids"] == [str(instructor_user.id)]


@pytest.mark.asyncio
async def test_open_call_without_user_ids_is_unrestricted(db, client, operations_headers):
    session = await _make_session(db)
    await db.commit()

    resp = await client.post(
        f"/sessions/{session.id}/staffing/open-call", headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["target_user_ids"] == []


@pytest.mark.asyncio
async def test_available_sessions_hides_a_call_you_are_not_targeted_for(
    db, client, operations_headers, instructor_headers, instructor_user: User,
):
    session = await _make_session(db)
    await db.commit()

    other = User(
        id=uuid.uuid4(), full_name="Untargeted Instructor",
        email=f"untargeted-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["instructor"],
    )
    db.add(other)
    await db.commit()

    await client.post(
        f"/sessions/{session.id}/staffing/open-call",
        json={"user_ids": [str(other.id)]},
        headers=operations_headers,
    )

    resp = await client.get("/sessions/available", headers=instructor_headers)
    assert resp.status_code == 200, resp.text
    assert str(session.id) not in [row["session_id"] for row in resp.json()]


@pytest.mark.asyncio
async def test_untargeted_instructor_cannot_register_interest(
    db, client, operations_headers, instructor_headers,
):
    session = await _make_session(db)
    await db.commit()

    other = User(
        id=uuid.uuid4(), full_name="The Chosen One",
        email=f"chosen-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["instructor"],
    )
    db.add(other)
    await db.commit()

    await client.post(
        f"/sessions/{session.id}/staffing/open-call",
        json={"user_ids": [str(other.id)]},
        headers=operations_headers,
    )

    resp = await client.post(
        f"/sessions/{session.id}/staffing/interest", json={}, headers=instructor_headers,
    )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_reopen_keeps_targeting_unless_told_otherwise(
    db, client, operations_headers, instructor_user: User,
):
    session = await _make_session(db)
    await db.commit()

    await client.post(
        f"/sessions/{session.id}/staffing/open-call",
        json={"user_ids": [str(instructor_user.id)]},
        headers=operations_headers,
    )
    await client.post(
        f"/sessions/{session.id}/staffing/select",
        json={"user_ids": [str(instructor_user.id)], "role": "lead"},
        headers=operations_headers,
    )

    resp = await client.post(f"/sessions/{session.id}/staffing/reopen", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["target_user_ids"] == [str(instructor_user.id)]

    # An explicit empty list widens it to everyone.
    resp = await client.post(
        f"/sessions/{session.id}/staffing/reopen", json={"user_ids": []}, headers=operations_headers,
    )
    assert resp.status_code in (200, 409), resp.text


# ── Session title must reach the instructor (operator, 2026-07-26) ───────────
# Found live during a CEO presentation: instructors saw only program + cohort,
# never what the session actually was.

@pytest.mark.asyncio
async def test_available_sessions_include_the_session_title(
    db, client, operations_headers, instructor_headers,
):
    session = await _make_session(db)
    session.title = "Intro to Orbits"
    await db.commit()

    await client.post(
        f"/sessions/{session.id}/staffing/open-call", headers=operations_headers,
    )

    resp = await client.get("/sessions/available", headers=instructor_headers)
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json() if r["session_id"] == str(session.id))
    assert row["title"] == "Intro to Orbits"


@pytest.mark.asyncio
async def test_my_sessions_include_the_session_title(
    db, client, operations_headers, instructor_headers, instructor_user: User,
):
    session = await _make_session(db)
    session.title = "Payload Assembly"
    await db.commit()

    await client.post(
        f"/sessions/{session.id}/staffing/open-call", headers=operations_headers,
    )
    await client.post(
        f"/sessions/{session.id}/staffing/select",
        json={"user_ids": [str(instructor_user.id)], "role": "lead"},
        headers=operations_headers,
    )

    resp = await client.get("/sessions/mine", headers=instructor_headers)
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json() if r["session_id"] == str(session.id))
    assert row["title"] == "Payload Assembly"


@pytest.mark.asyncio
async def test_session_delivery_includes_title_and_material(
    db, client, operations_headers, instructor_headers, instructor_user: User,
):
    """The portal an instructor stands in front of while teaching."""
    session = await _make_session(db)
    session.title = "Ground Station Setup"
    session.material_url = "https://example.test/slides.pdf"
    await db.commit()

    await client.post(
        f"/sessions/{session.id}/staffing/open-call", headers=operations_headers,
    )
    await client.post(
        f"/sessions/{session.id}/staffing/select",
        json={"user_ids": [str(instructor_user.id)], "role": "lead"},
        headers=operations_headers,
    )

    resp = await client.get(f"/sessions/{session.id}/delivery", headers=instructor_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "Ground Station Setup"
    assert body["material_url"] == "https://example.test/slides.pdf"
