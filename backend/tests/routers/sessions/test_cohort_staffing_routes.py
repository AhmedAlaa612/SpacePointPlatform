"""Endpoint tests for cohort-level staffing (2026-08-24).

Role guards on every new endpoint, plus the two behaviours that are easy to
get wrong at the HTTP boundary: a targeted cohort call must 404 (never 403)
for an instructor it doesn't target, and `/sessions/available-work` must not
list the same session twice.

Uses the shared Redis-free `client` — never a local one (see HANDOFF §8.9).
Basename is `test_cohort_staffing_routes.py`: test file basenames must be
unique across the whole suite, and `test_cohort_staffing.py` already exists
under tests/services/sessions/.
"""

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.user import User

from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_call import CohortCallTarget
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.services.sessions import staffing


@pytest_asyncio.fixture
async def admin_headers(db) -> dict:
    """`admin` passes every RequireRole check — asserted below so nobody is
    tempted to add a per-route admin bypass (HANDOFF §8.2)."""
    user = User(
        id=uuid.uuid4(), full_name="Test Admin",
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"),
        roles=["admin"], status="active",
    )
    db.add(user)
    await db.flush()
    return {"Authorization": f"Bearer {create_access_token(user.id, ['admin'])}"}


async def _other_instructor(db) -> User:
    """A real row — `cohort_call_targets.user_id` is a FK, so a bare uuid4
    can't stand in for somebody else."""
    user = User(
        id=uuid.uuid4(), full_name="Someone Else",
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"),
        roles=["instructor"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _make_cohort(db, session_count: int = 2) -> tuple[Cohort, list[Session]]:
    program = Program(
        id=uuid.uuid4(), code=f"CSR-{uuid.uuid4().hex[:8]}", name="Cohort Staffing Routes",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Routes Cohort",
        status="planned", visibility="public",
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


async def _open_call(db, cohort, sessions, target_user_ids=None):
    call, _ok, _failed = await staffing.open_cohort_call(
        db, cohort.id, session_ids=[s.id for s in sessions], target_user_ids=target_user_ids,
    )
    await db.commit()
    return call


# ── role guards ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_listing_applicants_requires_operations(db, client, instructor_headers):
    cohort, sessions = await _make_cohort(db)
    call = await _open_call(db, cohort, sessions)
    resp = await client.get(
        f"/sessions/cohorts/{cohort.id}/staffing/calls/{call.id}/interest",
        headers=instructor_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_select_for_cohort_requires_operations(db, client, instructor_headers):
    cohort, _sessions = await _make_cohort(db)
    await db.commit()
    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/staffing/select",
        json={"user_ids": [str(uuid.uuid4())]}, headers=instructor_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_listing_assignments_requires_operations(db, client, instructor_headers):
    cohort, _sessions = await _make_cohort(db)
    await db.commit()
    resp = await client.get(
        f"/sessions/cohorts/{cohort.id}/staffing/assignments", headers=instructor_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_passes_the_operations_guard(db, client, admin_headers):
    """`admin` passes every RequireRole check — never add a per-route bypass."""
    cohort, _sessions = await _make_cohort(db)
    await db.commit()
    resp = await client.get(
        f"/sessions/cohorts/{cohort.id}/staffing/assignments", headers=admin_headers
    )
    assert resp.status_code == 200


# ── targeting is a real restriction, and 404s rather than leaking ───────────

@pytest.mark.asyncio
async def test_untargeted_instructor_cannot_see_or_join_a_targeted_call(
    db, client, instructor_headers, instructor_user
):
    cohort, sessions = await _make_cohort(db)
    somebody_else = await _other_instructor(db)
    call = await _open_call(db, cohort, sessions, target_user_ids=[somebody_else.id])

    listed = await client.get("/sessions/available-work", headers=instructor_headers)
    assert listed.status_code == 200
    assert [c for c in listed.json()["cohort_calls"] if c["cohort_call_id"] == str(call.id)] == []

    joined = await client.post(
        f"/sessions/cohorts/{cohort.id}/staffing/calls/{call.id}/interest",
        json={"session_ids": [str(sessions[0].id)]}, headers=instructor_headers,
    )
    # 404, not 403 — don't leak which cohorts exist.
    assert joined.status_code == 404


@pytest.mark.asyncio
async def test_targeted_instructor_sees_the_call(db, client, instructor_headers, instructor_user):
    cohort, sessions = await _make_cohort(db)
    call = await _open_call(db, cohort, sessions, target_user_ids=[instructor_user.id])

    resp = await client.get("/sessions/available-work", headers=instructor_headers)
    assert resp.status_code == 200
    ids = [c["cohort_call_id"] for c in resp.json()["cohort_calls"]]
    assert str(call.id) in ids


# ── the cohort feed and the single-session feed must not overlap ────────────

@pytest.mark.asyncio
async def test_a_session_in_a_cohort_call_is_not_also_listed_as_a_single(
    db, client, instructor_headers
):
    cohort, sessions = await _make_cohort(db)
    call = await _open_call(db, cohort, sessions)

    resp = await client.get("/sessions/available-work", headers=instructor_headers)
    assert resp.status_code == 200
    body = resp.json()
    card = next(c for c in body["cohort_calls"] if c["cohort_call_id"] == str(call.id))
    grouped = {s["session_id"] for s in card["sessions"]}
    singles = {s["session_id"] for s in body["single_sessions"]}
    assert grouped, "the card should carry its sessions"
    assert grouped & singles == set(), "a session must appear in exactly one of the two lists"


@pytest.mark.asyncio
async def test_registering_then_withdrawing_round_trips(db, client, instructor_headers):
    cohort, sessions = await _make_cohort(db)
    call = await _open_call(db, cohort, sessions)

    created = await client.post(
        f"/sessions/cohorts/{cohort.id}/staffing/calls/{call.id}/interest",
        json={
            "session_ids": [str(sessions[0].id)],
            "needs_transport": True,
            "travelling_from_other_city": True,
            "note": "happy to take the early days",
        },
        headers=instructor_headers,
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["session_count"] == 1
    assert payload["needs_transport"] is True

    listed = await client.get("/sessions/available-work", headers=instructor_headers)
    card = next(c for c in listed.json()["cohort_calls"] if c["cohort_call_id"] == str(call.id))
    assert card["my_interest"] is True
    assert [s for s in card["sessions"] if s["selected"]][0]["session_id"] == str(sessions[0].id)

    gone = await client.delete(
        f"/sessions/cohorts/{cohort.id}/staffing/calls/{call.id}/interest",
        headers=instructor_headers,
    )
    assert gone.status_code == 204

    listed = await client.get("/sessions/available-work", headers=instructor_headers)
    card = next(c for c in listed.json()["cohort_calls"] if c["cohort_call_id"] == str(call.id))
    assert card["my_interest"] is False


@pytest.mark.asyncio
async def test_selecting_a_second_role_in_one_cohort_returns_409(
    db, client, operations_headers, instructor_user
):
    cohort, sessions = await _make_cohort(db)
    await db.commit()
    lead = await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == "Lead Facilitator"))
    assistant = await db.scalar(
        select(DeliveryRole.id).where(DeliveryRole.name == "Assistant Facilitator")
    )

    first = await client.post(
        f"/sessions/cohorts/{cohort.id}/staffing/select",
        json={"user_ids": [str(instructor_user.id)], "role_id": str(lead),
              "session_ids": [str(sessions[0].id)]},
        headers=operations_headers,
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        f"/sessions/cohorts/{cohort.id}/staffing/select",
        json={"user_ids": [str(instructor_user.id)], "role_id": str(assistant),
              "session_ids": [str(sessions[1].id)]},
        headers=operations_headers,
    )
    assert second.status_code == 409
    assert "Lead Facilitator" in second.json()["detail"]
