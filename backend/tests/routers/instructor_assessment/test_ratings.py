"""Post-program rating routes (2026-09): autosave-then-submit, and the
submit-lock ratchet (same contract as CompetitionScore.submitted)."""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.instructor_assessment.rating import RATING_DIMENSIONS
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
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
