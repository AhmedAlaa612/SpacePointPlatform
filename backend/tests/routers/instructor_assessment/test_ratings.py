"""Post-program rating routes (2026-09): autosave-then-submit, and the
submit-lock ratchet (same contract as CompetitionScore.submitted)."""

import uuid
from datetime import date

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.instructor_assessment.rating import RATING_DIMENSIONS
from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Rating Test Ops", email=f"rops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _instructor(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Rating Test Instructor", email=f"rinst-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["instructor"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"RATE-{uuid.uuid4().hex[:8]}", name="Rating Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Rating Test Cohort", status="planned", visibility="public")
    db.add(cohort)
    await db.flush()
    return cohort


def _full_scores(value: int = 4) -> dict:
    return {key: value for key in RATING_DIMENSIONS}


@pytest.mark.asyncio
async def test_upsert_rating_autosaves_as_draft(db, client):
    ops = await _ops(db)
    instructor = await _instructor(db)
    cohort = await _cohort(db)
    await db.commit()

    resp = await client.put(
        f"/instructor-assessment/ratings/{cohort.id}/{instructor.id}",
        json={"dimension_scores": _full_scores(4), "submit": False},
        headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_200_OK
    body = resp.json()
    assert body["submitted"] is False
    assert body["overall_rating"] == 4.0


@pytest.mark.asyncio
async def test_rating_cannot_be_edited_after_submit(db, client):
    ops = await _ops(db)
    instructor = await _instructor(db)
    cohort = await _cohort(db)
    await db.commit()

    await client.put(
        f"/instructor-assessment/ratings/{cohort.id}/{instructor.id}",
        json={"dimension_scores": _full_scores(5), "submit": True},
        headers=_headers(ops),
    )
    resp = await client.put(
        f"/instructor-assessment/ratings/{cohort.id}/{instructor.id}",
        json={"dimension_scores": _full_scores(1), "submit": False},
        headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_rating_requires_all_ten_dimensions(db, client):
    ops = await _ops(db)
    instructor = await _instructor(db)
    cohort = await _cohort(db)
    await db.commit()

    incomplete = _full_scores(3)
    incomplete.pop(RATING_DIMENSIONS[0])
    resp = await client.put(
        f"/instructor-assessment/ratings/{cohort.id}/{instructor.id}",
        json={"dimension_scores": incomplete, "submit": False},
        headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_submitted_rating_can_be_edited_with_submit_true(db, client):
    ops1 = await _ops(db)
    ops2 = await _ops(db)
    instructor = await _instructor(db)
    cohort = await _cohort(db)
    await db.commit()

    first = await client.put(
        f"/instructor-assessment/ratings/{cohort.id}/{instructor.id}",
        json={"dimension_scores": _full_scores(5), "submit": True},
        headers=_headers(ops1),
    )
    assert first.status_code == http_status.HTTP_200_OK
    assert first.json()["overall_rating"] == 5.0

    edited = await client.put(
        f"/instructor-assessment/ratings/{cohort.id}/{instructor.id}",
        json={
            "dimension_scores": _full_scores(3),
            "strengths": "Updated facilitation notes",
            "recommended": True,
            "flag": "exceptional",
            "submit": True,
        },
        headers=_headers(ops2),
    )
    assert edited.status_code == http_status.HTTP_200_OK
    body = edited.json()
    assert body["submitted"] is True
    assert body["overall_rating"] == 3.0
    assert body["strengths"] == "Updated facilitation notes"
    assert body["flag"] == "exceptional"

    fetched = await client.get(
        f"/instructor-assessment/ratings/{cohort.id}/{instructor.id}",
        headers=_headers(ops2),
    )
    assert fetched.status_code == http_status.HTTP_200_OK
    assert fetched.json()["overall_rating"] == 3.0


@pytest.mark.asyncio
async def test_certified_toggle_updates_auth_me_and_performance(db, client):
    ops = await _ops(db)
    instructor = await _instructor(db)
    await db.commit()

    me_before = await client.get("/auth/me", headers=_headers(instructor))
    assert me_before.status_code == http_status.HTTP_200_OK
    assert me_before.json()["is_certified_instructor"] is False

    on_resp = await client.put(
        f"/instructor-assessment/performance/{instructor.id}/certified",
        json={"certified": True},
        headers=_headers(ops),
    )
    assert on_resp.status_code == http_status.HTTP_200_OK
    assert on_resp.json()["is_certified"] is True

    me_after = await client.get("/auth/me", headers=_headers(instructor))
    assert me_after.status_code == http_status.HTTP_200_OK
    assert me_after.json()["is_certified_instructor"] is True

    off_resp = await client.put(
        f"/instructor-assessment/performance/{instructor.id}/certified",
        json={"certified": False},
        headers=_headers(ops),
    )
    assert off_resp.status_code == http_status.HTTP_200_OK
    assert off_resp.json()["is_certified"] is False

    me_final = await client.get("/auth/me", headers=_headers(instructor))
    assert me_final.status_code == http_status.HTTP_200_OK
    assert me_final.json()["is_certified_instructor"] is False


@pytest.mark.asyncio
async def test_ops_roster_returns_docs_boolean_and_card_id_without_sensitive_fields(db, client):
    ops = await _ops(db)
    instructor = await _instructor(db)
    instructor.card_number = 7301
    await db.commit()

    resp = await client.get("/instructor-assessment/performance", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_200_OK
    rows = resp.json()
    match = next((r for r in rows if r["id"] == str(instructor.id)), None)
    assert match is not None
    assert match["card_id"] == "SP-7301-UAE"
    assert isinstance(match["docs_complete"], bool)
    for forbidden in ("missing_docs", "documents", "bank_iban", "iban", "total_earned_aed"):
        assert forbidden not in match


@pytest.mark.asyncio
async def test_performance_includes_dimension_averages_and_direct_session_cohort_history(db, client):
    ops = await _ops(db)
    instructor = await _instructor(db)
    cohort = await _cohort(db)

    role = await db.scalar(select(DeliveryRole))
    if role is None:
        role = DeliveryRole(id=uuid.uuid4(), name=f"Lead {uuid.uuid4().hex[:6]}")
        db.add(role)
        await db.flush()

    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 10, 12))
    db.add(session)
    await db.flush()
    db.add(SessionInstructor(session_id=session.id, user_id=instructor.id, role_id=role.id))
    await db.commit()

    scores = _full_scores(4)
    scores[RATING_DIMENSIONS[0]] = 5
    await client.put(
        f"/instructor-assessment/ratings/{cohort.id}/{instructor.id}",
        json={"dimension_scores": scores, "submit": True},
        headers=_headers(ops),
    )

    perf_resp = await client.get(f"/instructor-assessment/performance/{instructor.id}", headers=_headers(ops))
    assert perf_resp.status_code == http_status.HTTP_200_OK
    perf = perf_resp.json()
    assert perf["dimension_averages"][RATING_DIMENSIONS[0]] == 5.0
    assert perf["dimension_averages"][RATING_DIMENSIONS[1]] == 4.0

    cohort_row = next((c for c in perf["cohort_history"] if c["cohort_id"] == str(cohort.id)), None)
    assert cohort_row is not None
    assert cohort_row["staffing_source"] == "Direct Assigned"
    assert cohort_row["sessions_assigned"] == 1
    assert cohort_row["rating"] is not None
    assert cohort_row["rating"]["overall_rating"] == 4.1
