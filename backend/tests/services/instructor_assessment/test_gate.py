"""The assessment gate on registering interest (2026-09): a cohort with no
assignment behaves exactly as before; a gated cohort blocks a *new*
registration until a submitted attempt exists; an instructor who already
registered before the gate existed is never retroactively blocked
(grandfathering).
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.instructor_assessment.config import AssessmentConfig, AssessmentQuestion
from app.models.sessions.cohort import Cohort
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User
from app.services.instructor_assessment import attempts as attempts_svc
from app.services.sessions import staffing


async def _make_user(db, roles=("instructor",), **overrides) -> User:
    defaults = dict(
        id=uuid.uuid4(), full_name="Test Instructor", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=list(roles),
    )
    defaults.update(overrides)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    return user


async def _make_open_session(db) -> Session:
    program = Program(
        id=uuid.uuid4(), code=f"GATE-{uuid.uuid4().hex[:8]}", name="Gate Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Gate Test Cohort", status="planned", visibility="public")
    db.add(cohort)
    await db.flush()
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 8, 10))
    db.add(session)
    await db.flush()
    await staffing.open_call(db, session.id)
    await db.flush()
    return session


async def _assign_assessment(db, cohort_id) -> AssessmentConfig:
    config = AssessmentConfig(id=uuid.uuid4(), name="Gate Test Assessment", is_active=True)
    db.add(config)
    await db.flush()
    for i in range(attempts_svc.DRAW_SIZE):
        db.add(AssessmentQuestion(
            id=uuid.uuid4(), config_id=config.id, category="General", prompt=f"Q{i}",
            options=[{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}],
            critical=False, is_active=True,
        ))
    db.add(AssessmentCohortAssignment(id=uuid.uuid4(), cohort_id=cohort_id, config_id=config.id))
    await db.flush()
    return config


@pytest.mark.asyncio
async def test_register_interest_unaffected_when_no_assessment_assigned(db):
    """Default behavior for every existing/new cohort: nothing changes."""
    session = await _make_open_session(db)
    user = await _make_user(db)
    interest = await staffing.register_interest(db, session.id, user)
    assert interest is not None


@pytest.mark.asyncio
async def test_register_interest_blocked_when_gated_and_no_attempt(db):
    session = await _make_open_session(db)
    await _assign_assessment(db, session.cohort_id)
    user = await _make_user(db)

    with pytest.raises(HTTPException) as exc:
        await staffing.register_interest(db, session.id, user)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_register_interest_succeeds_after_submitted_attempt(db):
    session = await _make_open_session(db)
    await _assign_assessment(db, session.cohort_id)
    user = await _make_user(db)

    from app.services.instructor_assessment.gate import resolve_cohort_call_id_for_session

    cohort_call_id = await resolve_cohort_call_id_for_session(db, session.id)
    attempt = await attempts_svc.start_attempt(db, cohort_call_id=cohort_call_id, user=user)
    await attempts_svc.submit_attempt(db, attempt, {})

    interest = await staffing.register_interest(db, session.id, user)
    assert interest is not None


@pytest.mark.asyncio
async def test_existing_interest_is_not_retroactively_gated(db):
    """An instructor who registered before the cohort opted into an
    assessment keeps working — updating their existing interest never
    triggers the gate."""
    session = await _make_open_session(db)
    user = await _make_user(db)
    await staffing.register_interest(db, session.id, user, note="before the gate existed")

    await _assign_assessment(db, session.cohort_id)

    # Updating the same interest (no attempt taken) must still succeed.
    interest = await staffing.register_interest(db, session.id, user, note="updated note")
    assert interest.note == "updated note"
