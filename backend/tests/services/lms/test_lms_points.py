"""P2-2/P2-3 (LMS Phase 2 Stage 2, 2026-08-10) — the points ledger and the
quiz-answer-oracle fix (audit §9.2). Redis-free, HTTP-free.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.lms import Course, CourseModule, ItemProgress, ModuleItem, PointEvent
from app.models.user import User
from app.services.lms import submit_quiz
from app.services.lms.points import (
    QUIZ_PASS_POINTS,
    QUIZ_PASS_POINTS_WITH_HINTS,
    award_points,
    award_quiz_points,
)
from app.services.lms.quiz import check_quiz_answer


async def _user(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Points Student", email=f"points-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _course(db, *, author=None) -> Course:
    author = author or await _user(db)
    course = Course(id=uuid.uuid4(), title=f"Course {uuid.uuid4().hex[:8]}", created_by=author.id)
    db.add(course)
    await db.flush()
    return course


async def _module(db, course) -> CourseModule:
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    return module


def _quiz_item(module, *, threshold, questions) -> ModuleItem:
    return ModuleItem(
        id=uuid.uuid4(), module_id=module.id, position=1, kind="quiz",
        content={"pass_threshold": threshold, "questions": questions},
    )


def _q(prompt, options):
    return {"prompt": prompt, "explanation": "because", "options": options}


async def _points_total(db, user_id) -> int:
    rows = (await db.execute(select(PointEvent.points).where(PointEvent.user_id == user_id))).scalars().all()
    return sum(rows)


# ── award_points: the generic ledger primitive ──────────────────────────────

@pytest.mark.asyncio
async def test_award_points_mints_a_row(db):
    student = await _user(db)
    event = await award_points(db, user_id=student.id, source="quiz", points=50, idempotency_key="item-1")
    assert event is not None
    assert event.points == 50


@pytest.mark.asyncio
async def test_award_points_replay_is_a_noop(db):
    student = await _user(db)
    first = await award_points(db, user_id=student.id, source="quiz", points=50, idempotency_key="item-1")
    second = await award_points(db, user_id=student.id, source="quiz", points=50, idempotency_key="item-1")
    assert first is not None
    assert second is None  # no error, no second row

    rows = (await db.execute(select(PointEvent).where(PointEvent.user_id == student.id))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_award_points_zero_or_negative_is_a_noop(db):
    student = await _user(db)
    assert await award_points(db, user_id=student.id, source="quiz", points=0, idempotency_key="x") is None
    assert await award_points(db, user_id=student.id, source="quiz", points=-5, idempotency_key="y") is None


# ── award_quiz_points: the quiz-specific rule ───────────────────────────────

@pytest.mark.asyncio
async def test_award_quiz_points_full_amount_with_no_hints(db):
    student = await _user(db)
    item_id = uuid.uuid4()
    event = await award_quiz_points(
        db, user_id=student.id, item_id=item_id, first_score=100, hints_used_at_first_submit=0, pass_threshold=70,
    )
    assert event.points == QUIZ_PASS_POINTS


@pytest.mark.asyncio
async def test_award_quiz_points_reduced_amount_when_hints_were_used(db):
    student = await _user(db)
    item_id = uuid.uuid4()
    event = await award_quiz_points(
        db, user_id=student.id, item_id=item_id, first_score=100, hints_used_at_first_submit=3, pass_threshold=70,
    )
    assert event.points == QUIZ_PASS_POINTS_WITH_HINTS


@pytest.mark.asyncio
async def test_award_quiz_points_nothing_for_a_failed_first_attempt(db):
    student = await _user(db)
    item_id = uuid.uuid4()
    event = await award_quiz_points(
        db, user_id=student.id, item_id=item_id, first_score=40, hints_used_at_first_submit=0, pass_threshold=70,
    )
    assert event is None


@pytest.mark.asyncio
async def test_award_quiz_points_threshold_zero_always_passes(db):
    student = await _user(db)
    item_id = uuid.uuid4()
    event = await award_quiz_points(
        db, user_id=student.id, item_id=item_id, first_score=0, hints_used_at_first_submit=0, pass_threshold=0,
    )
    assert event.points == QUIZ_PASS_POINTS


# ── submit_quiz end-to-end: first-attempt-only, the actual oracle fix ──────

@pytest.mark.asyncio
async def test_first_passing_submission_awards_points_once(db):
    course = await _course(db)
    module = await _module(db, course)
    quiz = _quiz_item(module, threshold=70, questions=[
        _q("2+2?", [{"text": "5", "is_correct": False}, {"text": "4", "is_correct": True}]),
    ])
    db.add(quiz)
    await db.flush()
    student = await _user(db)

    await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[1])
    assert await _points_total(db, student.id) == QUIZ_PASS_POINTS

    row = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == student.id, ItemProgress.item_id == quiz.id)
    )).scalars().first()
    assert row.first_score == 100
    assert row.first_scored_at is not None

    # Resubmitting (still correct) never mints a second award — first_score
    # is already set, so award_quiz_points is never called again.
    await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[1])
    assert await _points_total(db, student.id) == QUIZ_PASS_POINTS


@pytest.mark.asyncio
async def test_gaming_the_review_sheet_earns_zero_points(db):
    """The exact exploit the audit fixed: submit garbage to read every
    correct_text off the review sheet, then submit the now-known-correct
    answers. best_score ends at 100 either way — points must not."""
    course = await _course(db)
    module = await _module(db, course)
    quiz = _quiz_item(module, threshold=70, questions=[
        _q("2+2?", [{"text": "5", "is_correct": False}, {"text": "4", "is_correct": True}]),
        _q("Sky?", [{"text": "Up", "is_correct": True}, {"text": "Down", "is_correct": False}]),
    ])
    db.add(quiz)
    await db.flush()
    student = await _user(db)

    garbage = await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[0, 1])
    assert garbage["passed"] is False
    assert garbage["questions"][0]["correct_text"] == "4"  # the leak the exploit relies on

    correct = await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[1, 0])
    assert correct["passed"] is True
    assert correct["best_score"] == 100.0

    # best_score says 100; points say the truth — the first attempt failed.
    assert await _points_total(db, student.id) == 0

    row = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == student.id, ItemProgress.item_id == quiz.id)
    )).scalars().first()
    assert row.first_score == 0  # the garbage attempt, frozen forever
    assert row.best_score == 100  # unaffected — still the student's own encouragement metric


@pytest.mark.asyncio
async def test_using_check_before_first_submit_reduces_but_does_not_zero_points(db):
    course = await _course(db)
    module = await _module(db, course)
    quiz = _quiz_item(module, threshold=70, questions=[
        _q("2+2?", [{"text": "5", "is_correct": False}, {"text": "4", "is_correct": True}]),
    ])
    db.add(quiz)
    await db.flush()
    student = await _user(db)

    await check_quiz_answer(db, user_id=student.id, item_id=quiz.id, question_index=0, answer=1)
    await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[1])

    assert await _points_total(db, student.id) == QUIZ_PASS_POINTS_WITH_HINTS

    row = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == student.id, ItemProgress.item_id == quiz.id)
    )).scalars().first()
    assert row.hints_used == 1
