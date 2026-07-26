"""Tests for graceful degradation when Redis/ARQ is unreachable (2026-07-24,
operator's laptop can't keep Docker running). Nothing here needs a real
Redis connection — get_arq_redis is overridden to return None directly,
proving every ARQ-touching route survives that instead of crashing, exactly
as app/main.py's lifespan now does for real when create_pool() fails.
"""

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.workers.settings import get_arq_redis


@pytest.fixture
async def client_no_redis(db):
    """Same shape as the other Redis-free client fixtures in this directory,
    except it also overrides get_arq_redis -> None, simulating exactly what
    app.state.arq_redis is when Redis was unreachable at startup."""
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


@pytest.mark.asyncio
async def test_public_registration_succeeds_when_redis_is_down(db, client_no_redis):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)

    resp = await client_no_redis.post(
        f"/public/register/{cohort.id}",
        json={
            "student_name": "Redis Down Student", "email": "redis.down@example.com",
            "phone": "0501234567", "city": "Dubai",
        },
    )
    assert resp.status_code == 201, resp.text

    registration = (await db.execute(
        select(Registration).where(Registration.cohort_id == cohort.id)
    )).scalars().first()
    assert registration is not None
    assert registration.ticket_sent_at is None  # nothing was ever enqueued to send it


@pytest.mark.asyncio
async def test_desk_registration_succeeds_when_redis_is_down(db, client_no_redis, operations_headers):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)

    resp = await client_no_redis.post(
        f"/sessions/cohorts/{cohort.id}/registrations",
        json={
            "student_name": "Desk Redis Down", "email": "desk.redis.down@example.com",
            "phone": "0507654321", "send_ticket_email": True,
        },
        headers=operations_headers,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_resend_ticket_reports_inline_send_when_redis_is_down(
    db, client_no_redis, operations_headers,
):
    program = await _make_program(db)
    cohort = await _make_cohort(db, program)
    reg_resp = await client_no_redis.post(
        f"/sessions/cohorts/{cohort.id}/registrations",
        json={
            "student_name": "Resend Test", "email": "resend.redis.down@example.com",
            "phone": "0509998877", "send_ticket_email": False,
        },
        headers=operations_headers,
    )
    registration_id = reg_resp.json()["id"]

    resp = await client_no_redis.post(
        f"/sessions/registrations/{registration_id}/resend-ticket", headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    # With no queue to hand it to, safe_enqueue runs the send in-process and
    # says so — "queued" would be a lie (no worker will ever pick it up) and
    # "unavailable" would be one too (the ticket genuinely does go out).
    assert resp.json()["status"] == "inline"


@pytest.mark.asyncio
async def test_health_worker_reports_down_when_arq_redis_is_none():
    previous = getattr(app.state, "arq_redis", "unset")
    app.state.arq_redis = None
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            resp = await c.get("/health/worker")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"status": "down", "last_heartbeat": None}
    finally:
        if previous != "unset":
            app.state.arq_redis = previous
