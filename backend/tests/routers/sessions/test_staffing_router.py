"""Endpoint tests for the staffing marketplace routers (V2 W4 S4-2).
Mandatory per the plan spec: role guards on every endpoint, and the
assignment email actually gets enqueued on select.

Everything here uses the shared Redis-free `client`. Exactly one test —
test_select_instructors_assigns_notifies_and_enqueues_email — takes
`arq_client`/`arq_redis` instead, because it asserts the job reached the
queue. Until I0-1b the whole file needed a live Redis, so a role-guard 403
couldn't be tested without a broker.
"""

import uuid
from datetime import date

import httpx
import pytest
from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models.notification import Notification
from app.models.sessions.cohort import Cohort
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.workers.settings import get_arq_redis


async def _role_id(db, name: str = "Lead Facilitator"):
    """I5-3: roles are rows now. The three are seeded by migration
    `c2a7b49e0022`, so tests look them up rather than inventing their own."""
    from sqlalchemy import select

    from app.models.sessions.delivery_role import DeliveryRole

    return await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))



# `client` (Redis-free) and `arq_client` (real ARQ pool) live in
# tests/conftest.py. The local copy that used to be here bound *every* test in
# this file to a live Redis, including ones that never enqueue anything (I0-1b).


async def _make_cohort_with_session(db, **session_overrides) -> tuple[Cohort, Session]:
    program = Program(
        id=uuid.uuid4(), code=f"STAFFR-{uuid.uuid4().hex[:8]}", name="Staffing Router Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Staffing Router Test Cohort", status="planned", visibility="public", location="Room 4")
    db.add(cohort)
    await db.flush()
    defaults = dict(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 1))
    defaults.update(session_overrides)
    session = Session(**defaults)
    db.add(session)
    await db.flush()
    return cohort, session


# ── Role guards ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_open_call_requires_operations(db, client, instructor_headers):
    _, session = await _make_cohort_with_session(db)
    resp = await client.post(f"/sessions/{session.id}/staffing/open-call", headers=instructor_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_select_requires_operations(db, client, instructor_headers):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    resp = await client.post(
        f"/sessions/{session.id}/staffing/select", json={"user_ids": [str(uuid.uuid4())]}, headers=instructor_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_register_interest_requires_instructor_or_facilitator(db, client, other_role_headers):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    resp = await client.post(f"/sessions/{session.id}/staffing/interest", json={}, headers=other_role_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_register_interest_allows_facilitator(db, client, facilitator_headers):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    resp = await client.post(f"/sessions/{session.id}/staffing/interest", json={"note": "pick me"}, headers=facilitator_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["note"] == "pick me"


@pytest.mark.asyncio
async def test_eligible_instructors_requires_operations(db, client, instructor_headers):
    _, session = await _make_cohort_with_session(db)
    resp = await client.get(f"/sessions/{session.id}/staffing/eligible-instructors", headers=instructor_headers)
    assert resp.status_code == 403


# ── Open call → interest → select happy path ────────────────────────────────

@pytest.mark.asyncio
async def test_open_call_notifies_all_instructors_and_facilitators(db, client, operations_headers, instructor_user, facilitator_user):
    _, session = await _make_cohort_with_session(db)
    resp = await client.post(f"/sessions/{session.id}/staffing/open-call", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["staffing_status"] == "open_call"

    notified_user_ids = set((await db.execute(
        select(Notification.user_id).where(Notification.type == "staffing_open_call")
    )).scalars().all())
    assert instructor_user.id in notified_user_ids
    assert facilitator_user.id in notified_user_ids


@pytest.mark.asyncio
async def test_eligible_instructors_lists_full_roster_with_interest_flag(db, client, operations_headers, instructor_user, facilitator_user):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")
    db.add(InstructorInterest(id=uuid.uuid4(), session_id=session.id, user_id=instructor_user.id, note="I'd love this"))
    await db.flush()

    resp = await client.get(f"/sessions/{session.id}/staffing/eligible-instructors", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    by_id = {row["user_id"]: row for row in resp.json()}
    assert by_id[str(instructor_user.id)]["interested"] is True
    assert by_id[str(instructor_user.id)]["note"] == "I'd love this"
    # Full roster, not interest-only — facilitator never registered interest
    # but must still be selectable per the operator's explicit requirement.
    assert by_id[str(facilitator_user.id)]["interested"] is False


@pytest.mark.asyncio
async def test_select_instructors_assigns_notifies_and_enqueues_email(db, arq_client, arq_redis, operations_headers, instructor_user):
    # arq_client (not client): asserts the assignment email reached the queue.
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")

    resp = await arq_client.post(
        f"/sessions/{session.id}/staffing/select",
        json={"user_ids": [str(instructor_user.id)], "role": "lead"},
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["assigned"] == [str(instructor_user.id)]
    assert body["without_interest"] == [str(instructor_user.id)]  # ops override, never registered interest

    assignment = (await db.execute(
        select(SessionInstructor).where(SessionInstructor.session_id == session.id, SessionInstructor.user_id == instructor_user.id)
    )).scalars().first()
    assert assignment is not None and assignment.role == "lead"

    notif = (await db.execute(
        select(Notification).where(Notification.user_id == instructor_user.id, Notification.type == "staffing_assigned")
    )).scalars().first()
    assert notif is not None

    queued_jobs = await arq_redis.zrange("arq:queue", 0, -1)
    assert len(queued_jobs) == 1


@pytest.mark.asyncio
async def test_select_with_select_all_multiple_users(db, client, operations_headers, instructor_user, facilitator_user):
    _, session = await _make_cohort_with_session(db, staffing_status="open_call")

    resp = await client.post(
        f"/sessions/{session.id}/staffing/select",
        json={"user_ids": [str(instructor_user.id), str(facilitator_user.id)], "role": "co"},
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text
    assert set(resp.json()["assigned"]) == {str(instructor_user.id), str(facilitator_user.id)}


@pytest.mark.asyncio
async def test_available_sessions_requires_instructor_or_facilitator(db, client, other_role_headers):
    resp = await client.get("/sessions/available", headers=other_role_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_available_sessions_shows_open_call_with_my_interest(db, client, instructor_headers, instructor_user):
    _, open_session = await _make_cohort_with_session(db, staffing_status="open_call")
    _, unstaffed_session = await _make_cohort_with_session(db, meeting_date=date(2026, 9, 2))

    resp = await client.get("/sessions/available", headers=instructor_headers)
    assert resp.status_code == 200, resp.text
    session_ids = {row["session_id"] for row in resp.json()}
    assert str(open_session.id) in session_ids
    assert str(unstaffed_session.id) not in session_ids

    interest_resp = await client.post(f"/sessions/{open_session.id}/staffing/interest", json={"note": "yes please"}, headers=instructor_headers)
    assert interest_resp.status_code == 201

    resp2 = await client.get("/sessions/available", headers=instructor_headers)
    row = next(r for r in resp2.json() if r["session_id"] == str(open_session.id))
    assert row["my_interest"] is True
    assert row["my_note"] == "yes please"
    assert row["interested_count"] == 1


@pytest.mark.asyncio
async def test_my_sessions_shows_only_assigned(db, client, operations_headers, instructor_headers, instructor_user):
    _, assigned_session = await _make_cohort_with_session(db, staffing_status="open_call")
    _, other_session = await _make_cohort_with_session(db, meeting_date=date(2026, 9, 3))

    resp = await client.post(
        f"/sessions/{assigned_session.id}/staffing/select",
        json={"user_ids": [str(instructor_user.id)], "role": "lead"},
        headers=operations_headers,
    )
    assert resp.status_code == 200, resp.text

    mine = await client.get("/sessions/mine", headers=instructor_headers)
    assert mine.status_code == 200, mine.text
    session_ids = {row["session_id"] for row in mine.json()}
    assert str(assigned_session.id) in session_ids
    assert str(other_session.id) not in session_ids


@pytest.mark.asyncio
async def test_reopen_after_staffed_then_removal_notifies(db, client, operations_headers, instructor_user):
    cohort, session = await _make_cohort_with_session(db, staffing_status="staffed")
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=instructor_user.id, role_id=await _role_id(db)))
    await db.flush()

    resp = await client.delete(f"/sessions/cohorts/{cohort.id}/sessions/{session.id}/instructors/{instructor_user.id}", headers=operations_headers)
    assert resp.status_code == 204

    notif = (await db.execute(
        select(Notification).where(Notification.user_id == instructor_user.id, Notification.type == "staffing_removed")
    )).scalars().first()
    assert notif is not None
