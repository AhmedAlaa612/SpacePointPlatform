"""P5-3 (LMS Phase 2 Stage 5, 2026-08-11) — the quiz mission kind, reusing
the LMS grader (`services/lms/quiz.py::grade_quiz`). Redis-free, HTTP-free.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.lms import PointEvent
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User
from app.services.missions import start_attempt
from app.services.missions.verifiers.quiz import submit_quiz_attempt


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Quiz Mission User", email=f"qm-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=roles or ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _q(prompt, options):
    return {"prompt": prompt, "explanation": "because", "options": options}


async def _quiz_mission(db, *, author, threshold=70, points=50) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Orbital Mechanics Check", slug=f"quiz-{uuid.uuid4().hex[:8]}",
        kind="quiz", authored_by=author.id, status="published",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=points,
        config={
            "pass_threshold": threshold,
            "questions": [_q("2+2?", [{"text": "5", "is_correct": False}, {"text": "4", "is_correct": True}])],
        },
    )
    db.add(variant)
    await db.flush()
    return mission, variant


async def _points_total(db, user_id) -> int:
    rows = (await db.execute(select(PointEvent.points).where(PointEvent.user_id == user_id))).scalars().all()
    return sum(rows)


@pytest.mark.asyncio
async def test_correct_answers_pass_and_award_points(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _quiz_mission(db, author=author)
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)

    decided, review = await submit_quiz_attempt(db, attempt=attempt, variant=variant, answers=[1])

    assert decided.status == "passed"
    assert review["score"] == 100.0
    assert review["passed"] is True
    assert await _points_total(db, student.id) == 50


@pytest.mark.asyncio
async def test_wrong_answers_fail_and_award_nothing(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _quiz_mission(db, author=author)
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)

    decided, review = await submit_quiz_attempt(db, attempt=attempt, variant=variant, answers=[0])

    assert decided.status == "failed"
    assert review["passed"] is False
    assert await _points_total(db, student.id) == 0


@pytest.mark.asyncio
async def test_review_sheet_reveals_correct_text_same_as_lms_quiz(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _quiz_mission(db, author=author)
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)

    _, review = await submit_quiz_attempt(db, attempt=attempt, variant=variant, answers=[0])
    assert review["questions"][0]["correct_text"] == "4"


@pytest.mark.asyncio
async def test_cannot_resubmit_a_decided_attempt(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _quiz_mission(db, author=author)
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    await submit_quiz_attempt(db, attempt=attempt, variant=variant, answers=[1])

    with pytest.raises(Exception):
        await submit_quiz_attempt(db, attempt=attempt, variant=variant, answers=[1])


@pytest.mark.asyncio
async def test_retrying_after_a_fail_is_a_new_attempt_and_can_still_score(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _quiz_mission(db, author=author)
    student = await _user(db)

    first = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    await submit_quiz_attempt(db, attempt=first, variant=variant, answers=[0])
    assert await _points_total(db, student.id) == 0

    second = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)
    assert second.id != first.id
    await submit_quiz_attempt(db, attempt=second, variant=variant, answers=[1])
    assert await _points_total(db, student.id) == 50


@pytest.mark.asyncio
async def test_threshold_zero_always_passes(db):
    author = await _user(db, roles=["operations"])
    mission, variant = await _quiz_mission(db, author=author, threshold=0)
    student = await _user(db)
    attempt = await start_attempt(db, user_id=student.id, mission_id=mission.id, variant_id=variant.id)

    decided, review = await submit_quiz_attempt(db, attempt=attempt, variant=variant, answers=[0])
    assert decided.status == "passed"
    assert review["passed"] is True
