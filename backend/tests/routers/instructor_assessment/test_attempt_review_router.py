"""Ops-facing "view answers" drill-down (2026-09): both the session-scoped
and cohort-call-scoped entry points resolve to the same review, gated to
operations rather than the instructor's own auth."""

import uuid
from datetime import date

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.instructor_assessment.config import AssessmentConfig, AssessmentQuestion
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User
from app.services.instructor_assessment import attempts as attempts_svc
from app.services.instructor_assessment.gate import resolve_cohort_call_id_for_session
from app.services.sessions import staffing


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Review Test Ops", email=f"revops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _instructor(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Review Test Instructor", email=f"revinst-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["instructor"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _open_session(db) -> Session:
    program = Program(
        id=uuid.uuid4(), code=f"REV-{uuid.uuid4().hex[:8]}", name="Review Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Review Test Cohort", status="planned", visibility="public")
    db.add(cohort)
    await db.flush()
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 10))
    db.add(session)
    await db.flush()
    await staffing.open_call(db, session.id)
    await db.flush()
    return session


async def _config_with_questions(db) -> AssessmentConfig:
    config = AssessmentConfig(id=uuid.uuid4(), name="Review Test Assessment", is_active=True, draw_size=3, critical_floor=0)
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
    await db.flush()
    return config


@pytest.mark.asyncio
async def test_ops_can_view_review_via_session_id(db, client):
    ops = await _ops(db)
    instructor = await _instructor(db)
    session = await _open_session(db)
    config = await _config_with_questions(db)
    db.add(AssessmentCohortAssignment(id=uuid.uuid4(), cohort_id=session.cohort_id, config_id=config.id))
    await db.flush()

    cohort_call_id = await resolve_cohort_call_id_for_session(db, session.id)
    attempt = await attempts_svc.start_attempt(db, cohort_call_id=cohort_call_id, user=instructor)
    await attempts_svc.submit_attempt(db, attempt, {})
    await db.commit()

    resp = await client.get(
        f"/instructor-assessment/attempts/sessions/{session.id}/instructors/{instructor.id}/review",
        headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_200_OK
    body = resp.json()
    assert body["total"] == 3
    assert len(body["questions"]) == 3
    assert all(q["rationale"] for q in body["questions"])


@pytest.mark.asyncio
async def test_ops_can_view_review_via_cohort_call_id(db, client):
    ops = await _ops(db)
    instructor = await _instructor(db)
    session = await _open_session(db)
    config = await _config_with_questions(db)
    db.add(AssessmentCohortAssignment(id=uuid.uuid4(), cohort_id=session.cohort_id, config_id=config.id))
    await db.flush()

    cohort_call_id = await resolve_cohort_call_id_for_session(db, session.id)
    attempt = await attempts_svc.start_attempt(db, cohort_call_id=cohort_call_id, user=instructor)
    await attempts_svc.submit_attempt(db, attempt, {})
    await db.commit()

    resp = await client.get(
        f"/instructor-assessment/attempts/cohort-calls/{cohort_call_id}/instructors/{instructor.id}/review",
        headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_200_OK
    assert resp.json()["id"] == str(attempt.id)


@pytest.mark.asyncio
async def test_review_404s_when_no_submitted_attempt(db, client):
    ops = await _ops(db)
    instructor = await _instructor(db)
    session = await _open_session(db)
    await db.commit()

    resp = await client.get(
        f"/instructor-assessment/attempts/sessions/{session.id}/instructors/{instructor.id}/review",
        headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_instructor_role_cannot_view_others_review(db, client):
    """This is the ops selection-screen drill-down, not the instructor's own
    results page — require_operations, not require_instructor_or_facilitator."""
    instructor = await _instructor(db)
    other = await _instructor(db)
    session = await _open_session(db)
    await db.commit()

    resp = await client.get(
        f"/instructor-assessment/attempts/sessions/{session.id}/instructors/{other.id}/review",
        headers=_headers(instructor),
    )
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN
