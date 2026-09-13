"""Assessment config admin routes (2026-09): draw_size/critical_floor are
per-config (previously a hardcoded 15/3 constant) — cover both the
create-time schema validation and the update-time merged-state check, since
a PATCH touching only one of the two fields can't be caught by the schema
alone."""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.instructor_assessment.config import AssessmentConfig
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Config Test Ops", email=f"cops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_create_config_defaults_to_fifteen_and_three(db, client):
    ops = await _ops(db)
    await db.commit()

    resp = await client.post(
        "/instructor-assessment/admin/configs", json={"name": "Default Draw Config"}, headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_201_CREATED
    body = resp.json()
    assert body["draw_size"] == 15
    assert body["critical_floor"] == 3


@pytest.mark.asyncio
async def test_create_config_with_custom_draw_settings(db, client):
    ops = await _ops(db)
    await db.commit()

    resp = await client.post(
        "/instructor-assessment/admin/configs",
        json={"name": "Short Quiz Config", "draw_size": 5, "critical_floor": 1},
        headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_201_CREATED
    body = resp.json()
    assert body["draw_size"] == 5
    assert body["critical_floor"] == 1


@pytest.mark.asyncio
async def test_create_config_rejects_critical_floor_over_draw_size(db, client):
    ops = await _ops(db)
    await db.commit()

    resp = await client.post(
        "/instructor-assessment/admin/configs",
        json={"name": "Invalid Config", "draw_size": 5, "critical_floor": 10},
        headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_update_config_rejects_partial_update_that_breaks_the_invariant(db, client):
    """A PATCH touching only critical_floor can't be caught by the body-level
    validator (which only sees fields both present in the same request) —
    the router must check the merged result against the row's existing,
    unmentioned draw_size."""
    ops = await _ops(db)
    await db.commit()

    create_resp = await client.post(
        "/instructor-assessment/admin/configs", json={"name": "Patch Test Config"}, headers=_headers(ops),
    )
    config_id = create_resp.json()["id"]

    resp = await client.patch(
        f"/instructor-assessment/admin/configs/{config_id}",
        json={"critical_floor": 20},  # default draw_size is 15 — 20 > 15
        headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_delete_config_removes_it(db, client):
    ops = await _ops(db)
    await db.commit()

    create_resp = await client.post(
        "/instructor-assessment/admin/configs", json={"name": "Deletable Config"}, headers=_headers(ops),
    )
    config_id = create_resp.json()["id"]

    resp = await client.delete(f"/instructor-assessment/admin/configs/{config_id}", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_204_NO_CONTENT

    follow_up = await client.get(f"/instructor-assessment/admin/configs/{config_id}", headers=_headers(ops))
    assert follow_up.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_config_rejects_when_assigned_to_a_cohort(db, client):
    """`assessment_cohort_assignments.config_id` is RESTRICT — a config that
    gates a cohort's registrations can't be deleted out from under it."""
    ops = await _ops(db)
    program = Program(
        id=uuid.uuid4(), code=f"CFG-{uuid.uuid4().hex[:8]}", name="Delete Config Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Delete Config Test Cohort", status="planned", visibility="public")
    db.add(cohort)
    await db.flush()
    config = AssessmentConfig(id=uuid.uuid4(), name="Assigned Config", is_active=True, draw_size=15, critical_floor=3)
    db.add(config)
    await db.flush()
    db.add(AssessmentCohortAssignment(id=uuid.uuid4(), cohort_id=cohort.id, config_id=config.id))
    await db.commit()

    resp = await client.delete(f"/instructor-assessment/admin/configs/{config.id}", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_409_CONFLICT
    assert "1 cohort" in resp.json()["detail"]
