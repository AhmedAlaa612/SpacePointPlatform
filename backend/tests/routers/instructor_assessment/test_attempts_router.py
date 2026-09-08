"""Attempt routes end-to-end (2026-09): start -> submit -> the post-submit
review that replaced live per-question feedback (see attempts_svc.
get_attempt_review's docstring for why it's post-submit only)."""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.instructor_assessment.config import AssessmentConfig, AssessmentQuestion
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_call import CohortCall
from app.models.sessions.program import Program
from app.models.user import User


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _instructor(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Attempt Test Instructor", email=f"attinst-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["instructor"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _gated_cohort_call(db) -> tuple[CohortCall, AssessmentConfig]:
    program = Program(
        id=uuid.uuid4(), code=f"ATT-{uuid.uuid4().hex[:8]}", name="Attempt Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Attempt Test Cohort", status="planned", visibility="public")
    db.add(cohort)
    await db.flush()
    call = CohortCall(id=uuid.uuid4(), cohort_id=cohort.id, status="open")
    db.add(call)
    await db.flush()

    config = AssessmentConfig(id=uuid.uuid4(), name="Attempt Test Config", is_active=True, draw_size=3, critical_floor=0)
    db.add(config)
    await db.flush()
    for i in range(6):
        db.add(AssessmentQuestion(
            id=uuid.uuid4(), config_id=config.id, category="Only", prompt=f"Question {i}",
            options=[
                {"text": "A", "is_correct": True}, {"text": "B", "is_correct": False},
                {"text": "C", "is_correct": False}, {"text": "D", "is_correct": False},
            ],
            critical=False, is_active=True, rationale=f"A is right on #{i}",
        ))
    db.add(AssessmentCohortAssignment(id=uuid.uuid4(), cohort_id=cohort.id, config_id=config.id))
    await db.flush()
    return call, config


@pytest.mark.asyncio
async def test_submit_response_includes_the_post_submit_review(db, client):
    instructor = await _instructor(db)
    call, _ = await _gated_cohort_call(db)
    await db.commit()

    start_resp = await client.post(
        f"/instructor-assessment/attempts/{call.id}/start", headers=_headers(instructor),
    )
    assert start_resp.status_code == http_status.HTTP_200_OK
    attempt = start_resp.json()
    assert len(attempt["questions"]) == 3
    # The pre-submit question payload never carries the answer or rationale —
    # that's the whole point of gating it to post-submit.
    assert "rationale" not in attempt["questions"][0]
    assert "is_correct" not in attempt["questions"][0]

    submit_resp = await client.post(
        f"/instructor-assessment/attempts/{attempt['id']}/submit",
        json={"answers": {}},  # left every question blank
        headers=_headers(instructor),
    )
    assert submit_resp.status_code == http_status.HTTP_200_OK
    result = submit_resp.json()
    assert result["score"] == 0
    assert len(result["questions"]) == 3
    for q in result["questions"]:
        assert q["is_correct"] is False
        assert q["selected_index"] is None
        assert q["correct_index"] is not None
        assert q["rationale"]
