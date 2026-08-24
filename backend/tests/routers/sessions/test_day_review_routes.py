"""Endpoint tests for the instructor daily loop.

Role guards, the don't-leak-existence 404, and one thing only an HTTP test can
catch: `/sessions/day-reviews` is a literal path competing with the
`/sessions/{session_id}/...` routers, so a mounting-order regression would
make it 422 on "day-reviews" not being a UUID.

Shared Redis-free `client` throughout (HANDOFF §8.9).
"""

import uuid
from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User


@pytest_asyncio.fixture
async def admin_headers(db) -> dict:
    user = User(
        id=uuid.uuid4(), full_name="Test Admin", email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"), roles=["admin"], status="active",
    )
    db.add(user)
    await db.flush()
    return {"Authorization": f"Bearer {create_access_token(user.id, ['admin'])}"}


async def _make(db, session_count: int = 1):
    program = Program(
        id=uuid.uuid4(), code=f"DR-{uuid.uuid4().hex[:8]}", name="Day Review Routes",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="DR Cohort",
        status="running", visibility="public",
    )
    db.add(cohort)
    await db.flush()
    sessions = []
    for i in range(session_count):
        s = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 10 + i))
        db.add(s)
        sessions.append(s)
    await db.flush()
    return cohort, sessions


async def _assign(db, session, user):
    role_id = await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == "Lead Facilitator"))
    db.add(SessionInstructor(
        id=uuid.uuid4(), session_id=session.id, user_id=user.id, role_id=role_id,
    ))
    await db.flush()


# ── mounting order ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_day_reviews_is_not_shadowed_by_the_session_id_routes(db, client, operations_headers):
    """A 422 here means `/sessions/{session_id}/...` was mounted first and
    tried to parse "day-reviews" as a UUID."""
    resp = await client.get("/sessions/day-reviews", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


# ── role guards ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_day_review_queue_requires_operations(db, client, instructor_headers):
    resp = await client.get("/sessions/day-reviews", headers=instructor_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_approve_requires_operations(db, client, instructor_headers):
    resp = await client.post(
        f"/sessions/day-reviews/{uuid.uuid4()}/approve", headers=instructor_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_return_requires_operations(db, client, instructor_headers):
    resp = await client.post(
        f"/sessions/day-reviews/{uuid.uuid4()}/return",
        json={"comment": "fix it"}, headers=instructor_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_setting_checklist_items_requires_operations(db, client, instructor_headers):
    cohort, _sessions = await _make(db)
    await db.commit()
    resp = await client.put(
        f"/sessions/cohorts/{cohort.id}/checklist-items",
        json={"items": [{"title": "Kits distributed"}]}, headers=instructor_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_passes_the_operations_guard(db, client, admin_headers):
    resp = await client.get("/sessions/day-reviews", headers=admin_headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_an_unknown_checklist_scope_404s(db, client, operations_headers):
    resp = await client.get(
        f"/sessions/widgets/{uuid.uuid4()}/checklist-items", headers=operations_headers
    )
    assert resp.status_code == 404


# ── the instructor's own routes ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unassigned_instructor_gets_404_on_someone_elses_session(
    db, client, instructor_headers
):
    _cohort, sessions = await _make(db)
    await db.commit()
    resp = await client.get(f"/sessions/{sessions[0].id}/delivery/day", headers=instructor_headers)
    assert resp.status_code == 404, "don't leak which sessions exist"


@pytest.mark.asyncio
async def test_full_day_round_trip_over_http(
    db, client, instructor_headers, instructor_user, operations_headers
):
    cohort, sessions = await _make(db)
    await _assign(db, sessions[0], instructor_user)
    await db.commit()

    ops_items = await client.put(
        f"/sessions/cohorts/{cohort.id}/checklist-items",
        json={"items": [{"title": "Kits distributed", "is_required": True}]},
        headers=operations_headers,
    )
    assert ops_items.status_code == 200, ops_items.text
    item_id = ops_items.json()[0]["id"]

    checked_in = await client.post(
        f"/sessions/{sessions[0].id}/delivery/check-in",
        json={"att_status": "present"}, headers=instructor_headers,
    )
    assert checked_in.status_code == 200, checked_in.text
    assert checked_in.json()["att_status"] == "present"
    assert checked_in.json()["can_submit"] is False

    ticked = await client.put(
        f"/sessions/{sessions[0].id}/delivery/checklist/{item_id}",
        json={"is_done": True}, headers=instructor_headers,
    )
    assert ticked.status_code == 200, ticked.text
    assert ticked.json()["can_submit"] is True

    submitted = await client.post(
        f"/sessions/{sessions[0].id}/delivery/day/submit",
        json={"notes": "went well"}, headers=instructor_headers,
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"

    queue = await client.get("/sessions/day-reviews", headers=operations_headers)
    assert queue.status_code == 200
    card = next(c for c in queue.json() if c["session_id"] == str(sessions[0].id))
    assert card["checklist_done"] == 1 and card["checklist_total"] == 1
    assert card["full_name"] == instructor_user.full_name

    returned = await client.post(
        f"/sessions/day-reviews/{card['day_id']}/return",
        json={"comment": "Add the setup photo"}, headers=operations_headers,
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "changes_required"

    await client.post(
        f"/sessions/{sessions[0].id}/delivery/day/submit", json={}, headers=instructor_headers
    )
    approved = await client.post(
        f"/sessions/day-reviews/{card['day_id']}/approve", headers=operations_headers
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_submitting_early_returns_409_listing_what_is_missing(
    db, client, instructor_headers, instructor_user, operations_headers
):
    cohort, sessions = await _make(db)
    await _assign(db, sessions[0], instructor_user)
    await db.commit()
    await client.put(
        f"/sessions/cohorts/{cohort.id}/checklist-items",
        json={"items": [{"title": "Kits distributed", "is_required": True}]},
        headers=operations_headers,
    )
    await client.post(
        f"/sessions/{sessions[0].id}/delivery/check-in",
        json={"att_status": "present"}, headers=instructor_headers,
    )
    resp = await client.post(
        f"/sessions/{sessions[0].id}/delivery/day/submit", json={}, headers=instructor_headers
    )
    assert resp.status_code == 409
    assert "Kits distributed" in resp.json()["detail"]
