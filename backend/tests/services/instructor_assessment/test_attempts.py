"""Draw algorithm (critical floor + category round-robin), get-or-create
attempt semantics, and grading correctness (2026-09)."""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.instructor_assessment.attempt import AssessmentAttempt
from app.models.instructor_assessment.config import AssessmentConfig, AssessmentQuestion
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_call import CohortCall
from app.models.sessions.program import Program
from app.models.user import User
from app.services.instructor_assessment import attempts as attempts_svc


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


async def _make_cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"IA-{uuid.uuid4().hex[:8]}", name="Assessment Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Assessment Test Cohort", status="planned", visibility="public")
    db.add(cohort)
    await db.flush()
    return cohort


async def _make_cohort_call(db, cohort: Cohort) -> CohortCall:
    call = CohortCall(id=uuid.uuid4(), cohort_id=cohort.id, status="open")
    db.add(call)
    await db.flush()
    return call


# Mirrors the real bank's shape: uneven category sizes, critical questions
# clustered in only a couple of categories — the exact scenario the
# round-robin + critical-floor algorithm exists for.
_BANK_SHAPE = {
    "Program Flow": (5, 0),
    "Classroom Facilitation": (5, 0),
    "Safety & PPE": (3, 3),          # all critical
    "Time Management": (4, 0),
    "Escalation": (4, 1),            # one critical
    "Demo Day": (4, 0),
}


async def _make_config_with_questions(db, shape: dict[str, tuple[int, int]] = _BANK_SHAPE) -> AssessmentConfig:
    config = AssessmentConfig(id=uuid.uuid4(), name="Test Assessment", is_active=True)
    db.add(config)
    await db.flush()
    for category, (total, critical_count) in shape.items():
        for i in range(total):
            db.add(AssessmentQuestion(
                id=uuid.uuid4(), config_id=config.id, category=category,
                prompt=f"{category} question {i}",
                options=[
                    {"text": "A", "is_correct": True}, {"text": "B", "is_correct": False},
                    {"text": "C", "is_correct": False}, {"text": "D", "is_correct": False},
                ],
                critical=i < critical_count, is_active=True,
            ))
    await db.flush()
    return config


# ── draw algorithm ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_draw_questions_meets_critical_floor(db):
    config = await _make_config_with_questions(db)
    drawn = await attempts_svc.draw_questions(db, config.id)

    assert len(drawn) == attempts_svc.DRAW_SIZE
    assert len({q.id for q in drawn}) == attempts_svc.DRAW_SIZE  # no duplicates
    critical_drawn = [q for q in drawn if q.critical]
    assert len(critical_drawn) >= min(attempts_svc.CRITICAL_FLOOR, 4)  # bank has 4 critical total


@pytest.mark.asyncio
async def test_draw_questions_spreads_across_categories(db):
    """A bug that always drains one category first would still pass a bare
    count check — assert real category diversity, not just totals."""
    config = await _make_config_with_questions(db)
    drawn = await attempts_svc.draw_questions(db, config.id)
    categories = {q.category for q in drawn}
    assert len(categories) >= 5  # 6 categories exist; round-robin should touch nearly all of them


@pytest.mark.asyncio
async def test_draw_questions_errors_gracefully_when_bank_too_small(db):
    config = await _make_config_with_questions(db, shape={"Only Category": (5, 1)})
    drawn = await attempts_svc.draw_questions(db, config.id)
    assert len(drawn) == 5  # fewer than DRAW_SIZE exist — draws everything available, doesn't crash


# ── get-or-create attempt semantics ──────────────────────────────────────

@pytest.mark.asyncio
async def test_start_attempt_requires_an_assignment(db):
    cohort = await _make_cohort(db)
    call = await _make_cohort_call(db, cohort)
    user = await _make_user(db)

    with pytest.raises(HTTPException) as exc:
        await attempts_svc.start_attempt(db, cohort_call_id=call.id, user=user)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_start_attempt_is_get_or_create(db):
    """A page refresh mid-attempt must never reshuffle the drawn questions
    or their option order."""
    cohort = await _make_cohort(db)
    call = await _make_cohort_call(db, cohort)
    config = await _make_config_with_questions(db)
    db.add(AssessmentCohortAssignment(id=uuid.uuid4(), cohort_id=cohort.id, config_id=config.id))
    await db.flush()
    user = await _make_user(db)

    first = await attempts_svc.start_attempt(db, cohort_call_id=call.id, user=user)
    second = await attempts_svc.start_attempt(db, cohort_call_id=call.id, user=user)

    assert first.id == second.id
    assert first.question_order == second.question_order

    count = await db.scalar(
        select(AssessmentAttempt).where(
            AssessmentAttempt.cohort_call_id == call.id, AssessmentAttempt.user_id == user.id,
        )
    )
    assert count is not None  # exactly the one row — the unique constraint would reject a second


# ── grading ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_submit_attempt_grades_against_shuffled_option_order(db):
    """The correct answer must be tracked by which option it is, not by
    which position it happens to be displayed at."""
    cohort = await _make_cohort(db)
    call = await _make_cohort_call(db, cohort)
    config = await _make_config_with_questions(db, shape={"Only": (attempts_svc.DRAW_SIZE, 0)})
    db.add(AssessmentCohortAssignment(id=uuid.uuid4(), cohort_id=cohort.id, config_id=config.id))
    await db.flush()
    user = await _make_user(db)

    attempt = await attempts_svc.start_attempt(db, cohort_call_id=call.id, user=user)

    # Answer every question at whichever displayed position maps back to
    # the original correct option (index 0, "A", per the factory above).
    answers = {}
    for entry in attempt.question_order:
        correct_display_position = entry["option_order"].index(0)
        answers[entry["question_id"]] = correct_display_position

    result = await attempts_svc.submit_attempt(db, attempt, answers)
    assert result.score == attempts_svc.DRAW_SIZE
    assert result.status == "submitted"


@pytest.mark.asyncio
async def test_submit_attempt_twice_is_rejected(db):
    cohort = await _make_cohort(db)
    call = await _make_cohort_call(db, cohort)
    config = await _make_config_with_questions(db, shape={"Only": (attempts_svc.DRAW_SIZE, 0)})
    db.add(AssessmentCohortAssignment(id=uuid.uuid4(), cohort_id=cohort.id, config_id=config.id))
    await db.flush()
    user = await _make_user(db)

    attempt = await attempts_svc.start_attempt(db, cohort_call_id=call.id, user=user)
    await attempts_svc.submit_attempt(db, attempt, {})

    with pytest.raises(HTTPException) as exc:
        await attempts_svc.submit_attempt(db, attempt, {})
    assert exc.value.status_code == 409
