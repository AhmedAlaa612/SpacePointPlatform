"""Endpoint tests for `open_cohort_call`'s `email_mode` (2026-09-13).

Covers the three things ops asked for: emails are opt-in (default "none")
regardless of whether the call is targeted or public, "all" fires exactly
ONE job for the whole cohort call rather than one per session it opened, and
the city-scoped modes actually filter who gets that job's recipient list.

Uses `arq_client`/`arq_redis` (not the Redis-free `client`) — every test here
asserts something about what did or didn't reach the queue.
"""

import uuid
from datetime import date

import pytest
import pytest_asyncio

from app.core.security import create_access_token, get_password_hash
from app.models.inventory.city import City
from app.models.inventory.location import Location
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User


async def _make_cohort(db, session_count: int = 2, location_id=None) -> tuple[Cohort, list[Session]]:
    program = Program(
        id=uuid.uuid4(), code=f"CEM-{uuid.uuid4().hex[:8]}", name="Email Mode Cohort",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Email Mode Cohort",
        status="planned", visibility="public", location_id=location_id,
    )
    db.add(cohort)
    await db.flush()
    sessions = []
    for i in range(session_count):
        s = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 11, 3 + i))
        db.add(s)
        sessions.append(s)
    await db.flush()
    return cohort, sessions


async def _location_with_city(db) -> Location:
    city = City(id=uuid.uuid4(), name=f"City-{uuid.uuid4().hex[:6]}", country="AE")
    db.add(city)
    await db.flush()
    location = Location(id=uuid.uuid4(), name=f"Loc-{uuid.uuid4().hex[:6]}", country="AE", city_id=city.id)
    db.add(location)
    await db.flush()
    return location


async def _other_city(db) -> uuid.UUID:
    """A real, unrelated city row — `User.city_id` is a real FK, unlike
    `ApplicantProfile.deliver_city_ids` which is a bare array with no FK
    enforcement, so a stray uuid4() doesn't work here."""
    city = City(id=uuid.uuid4(), name=f"Other-{uuid.uuid4().hex[:6]}", country="AE")
    db.add(city)
    await db.flush()
    return city.id


async def _make_instructor(db, *, city_id=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Test Instructor",
        email=f"instr-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"),
        roles=["instructor"], status="active", city_id=city_id,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_default_email_mode_queues_no_email_for_targeted_call(
    db, arq_client, arq_redis, operations_headers,
):
    """A targeted call used to always email its targets. Now email is its
    own opt-in choice — omitting `email_mode` must queue nothing."""
    cohort, sessions = await _make_cohort(db, session_count=2)
    target = await _make_instructor(db)

    resp = await arq_client.post(
        f"/sessions/cohorts/{cohort.id}/staffing/calls",
        json={"session_ids": [str(s.id) for s in sessions], "user_ids": [str(target.id)]},
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["call"]["sessions"]) == 2

    assert await arq_redis.zrange("arq:queue", 0, -1) == []


@pytest.mark.asyncio
async def test_email_mode_all_queues_exactly_one_job_for_the_whole_cohort(
    db, arq_client, arq_redis, operations_headers,
):
    """The bug this fixes: opening used to enqueue `send_call_invite_emails`
    once per session, so a targeted instructor got one email per session in
    the cohort call. With `email_mode="all"` across 2 sessions, exactly ONE
    job should land on the queue — one invite for the whole cohort run."""
    cohort, sessions = await _make_cohort(db, session_count=2)
    first = await _make_instructor(db)
    second = await _make_instructor(db)

    resp = await arq_client.post(
        f"/sessions/cohorts/{cohort.id}/staffing/calls",
        json={
            "session_ids": [str(s.id) for s in sessions],
            "user_ids": [str(first.id), str(second.id)],
            "email_mode": "all",
        },
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["call"]["sessions"]) == 2

    queued_jobs = await arq_redis.zrange("arq:queue", 0, -1)
    assert len(queued_jobs) == 1


@pytest.mark.asyncio
async def test_email_mode_same_city_only_queues_when_a_recipient_matches(
    db, arq_client, arq_redis, operations_headers,
):
    """A public (untargeted) call with `email_mode="same_city"` should still
    reach nobody when no instructor's home city matches the cohort's — city
    modes never silently fall back to "all"."""
    location = await _location_with_city(db)
    cohort, sessions = await _make_cohort(db, session_count=1, location_id=location.id)
    # No instructor anywhere has this city as their home city.
    await _make_instructor(db, city_id=await _other_city(db))

    resp = await arq_client.post(
        f"/sessions/cohorts/{cohort.id}/staffing/calls",
        json={"session_ids": [str(s.id) for s in sessions], "email_mode": "same_city"},
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text

    assert await arq_redis.zrange("arq:queue", 0, -1) == []


@pytest.mark.asyncio
async def test_email_mode_same_city_queues_one_job_when_a_recipient_matches(
    db, arq_client, arq_redis, operations_headers,
):
    location = await _location_with_city(db)
    cohort, sessions = await _make_cohort(db, session_count=1, location_id=location.id)
    await _make_instructor(db, city_id=location.city_id)  # matches
    await _make_instructor(db, city_id=await _other_city(db))  # doesn't match

    resp = await arq_client.post(
        f"/sessions/cohorts/{cohort.id}/staffing/calls",
        json={"session_ids": [str(s.id) for s in sessions], "email_mode": "same_city"},
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text

    queued_jobs = await arq_redis.zrange("arq:queue", 0, -1)
    assert len(queued_jobs) == 1
