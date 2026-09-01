"""Random-N quiz questions (2026-09-01) — services/lms/quiz.py::

get_quiz_display_order, and its threading through check_quiz_answer/
submit_quiz/serialize.student_view. Covers: unset/oversized random_count is
a no-op (today's full-pool behavior); a sample is drawn once and reused for
the rest of that attempt (a page refresh doesn't reshuffle); submitting
clears the sample so the next view draws a fresh one; grading and live-check
resolve strictly against the shown subset, never the raw authored pool
positions. Redis-free, HTTP-free — same posture as test_lms_services.py.
"""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.lms import Course, CourseModule, ItemProgress, ModuleItem
from app.models.user import User
from app.services.lms import check_quiz_answer, get_quiz_display_order, student_view, submit_quiz
from app.services.lms.quiz import random as quiz_random


async def _user(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="LMS Student",
        email=f"lms-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        roles=["student"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _course(db) -> Course:
    author = await _user(db)
    course = Course(id=uuid.uuid4(), title=f"Course {uuid.uuid4().hex[:8]}", created_by=author.id)
    db.add(course)
    await db.flush()
    return course


async def _module(db, course) -> CourseModule:
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="Module 1", position=1)
    db.add(module)
    await db.flush()
    return module


def _q(prompt, correct_text, wrong_text="Wrong", explanation="Because."):
    return {
        "prompt": prompt,
        "explanation": explanation,
        "options": [{"text": wrong_text, "is_correct": False}, {"text": correct_text, "is_correct": True}],
    }


async def _quiz_5q(db, module, *, random_count=None, pass_threshold=0) -> ModuleItem:
    questions = [_q(f"Q{i}?", f"Right{i}", f"Wrong{i}") for i in range(5)]
    item = ModuleItem(
        id=uuid.uuid4(),
        module_id=module.id,
        position=1,
        kind="quiz",
        content={"pass_threshold": pass_threshold, "questions": questions, "random_count": random_count},
    )
    db.add(item)
    await db.flush()
    return item


# ── get_quiz_display_order: the sampling policy itself ──────────────────────

@pytest.mark.asyncio
async def test_random_count_unset_returns_none_full_pool(db):
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _quiz_5q(db, m, random_count=None)
    student = await _user(db)

    order = await get_quiz_display_order(db, user_id=student.id, item=quiz)
    assert order is None


@pytest.mark.asyncio
async def test_random_count_at_or_above_pool_size_returns_none(db):
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _quiz_5q(db, m, random_count=5)
    student = await _user(db)

    assert await get_quiz_display_order(db, user_id=student.id, item=quiz) is None


@pytest.mark.asyncio
async def test_random_count_draws_a_valid_sample_of_the_right_size(db):
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _quiz_5q(db, m, random_count=3)
    student = await _user(db)

    order = await get_quiz_display_order(db, user_id=student.id, item=quiz)
    assert order is not None
    assert len(order) == 3
    assert len(set(order)) == 3  # no repeats
    assert all(0 <= i < 5 for i in order)


@pytest.mark.asyncio
async def test_sample_is_stable_across_repeated_views_of_the_same_attempt(db):
    """A page refresh mid-attempt must not reshuffle the questions out from
    under the student's in-progress answers."""
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _quiz_5q(db, m, random_count=3)
    student = await _user(db)

    first = await get_quiz_display_order(db, user_id=student.id, item=quiz)
    second = await get_quiz_display_order(db, user_id=student.id, item=quiz)
    third = await get_quiz_display_order(db, user_id=student.id, item=quiz)
    assert first == second == third


@pytest.mark.asyncio
async def test_different_students_can_get_different_samples(db, monkeypatch):
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _quiz_5q(db, m, random_count=3)
    alice = await _user(db)
    bob = await _user(db)

    calls = iter([[0, 1, 2], [2, 3, 4]])
    monkeypatch.setattr(quiz_random, "sample", lambda pop, k: next(calls))

    alice_order = await get_quiz_display_order(db, user_id=alice.id, item=quiz)
    bob_order = await get_quiz_display_order(db, user_id=bob.id, item=quiz)
    assert alice_order == [0, 1, 2]
    assert bob_order == [2, 3, 4]
    assert alice_order != bob_order


@pytest.mark.asyncio
async def test_submit_clears_the_sample_so_the_next_view_draws_fresh(db, monkeypatch):
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _quiz_5q(db, m, random_count=3)
    student = await _user(db)

    calls = iter([[0, 1, 2], [1, 2, 3]])
    monkeypatch.setattr(quiz_random, "sample", lambda pop, k: next(calls))

    first_order = await get_quiz_display_order(db, user_id=student.id, item=quiz)
    assert first_order == [0, 1, 2]

    # Answer the 3 shown questions (indices 0,1,2 -> correct option is 1).
    await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[1, 1, 1])

    row = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == student.id, ItemProgress.item_id == quiz.id)
    )).scalars().first()
    assert row.quiz_question_order is None

    second_order = await get_quiz_display_order(db, user_id=student.id, item=quiz)
    assert second_order == [1, 2, 3]
    assert second_order != first_order


# ── grading/live-check resolve against the shown subset, not raw positions ──

@pytest.mark.asyncio
async def test_submit_grades_only_the_shown_subset_in_shown_order(db, monkeypatch):
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _quiz_5q(db, m, random_count=3, pass_threshold=100)
    student = await _user(db)

    # Sampled subset (in this order): question 4, question 1, question 0.
    monkeypatch.setattr(quiz_random, "sample", lambda pop, k: [4, 1, 0])
    order = await get_quiz_display_order(db, user_id=student.id, item=quiz)
    assert order == [4, 1, 0]

    # answers is positional against the SHOWN order, correct option is index 1.
    result = await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[1, 1, 1])
    assert result["score"] == 100.0
    assert result["passed"] is True
    assert [q["prompt"] for q in result["questions"]] == ["Q4?", "Q1?", "Q0?"]

    # Only 3 answers required, not 5 — proves grading isn't against the full pool.
    with pytest.raises(HTTPException) as e:
        await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[1, 1, 1, 1, 1])
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_check_quiz_answer_resolves_through_the_sampled_order(db, monkeypatch):
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _quiz_5q(db, m, random_count=2)
    student = await _user(db)

    # Shown subset: question 3 first, then question 0.
    monkeypatch.setattr(quiz_random, "sample", lambda pop, k: [3, 0])
    await get_quiz_display_order(db, user_id=student.id, item=quiz)

    # question_index 0 (the first shown question) is really question 3.
    result = await check_quiz_answer(db, user_id=student.id, item_id=quiz.id, question_index=0, answer=1)
    assert result["correct"] is True
    assert result["correct_text"] == "Right3"

    # question_index 2 doesn't exist in a 2-question shown set.
    with pytest.raises(HTTPException) as e:
        await check_quiz_answer(db, user_id=student.id, item_id=quiz.id, question_index=2, answer=1)
    assert e.value.status_code == 400


# ── student_view: the served payload only carries the sampled subset ───────

@pytest.mark.asyncio
async def test_student_view_serves_only_the_sampled_subset(db, monkeypatch):
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _quiz_5q(db, m, random_count=2)
    student = await _user(db)

    monkeypatch.setattr(quiz_random, "sample", lambda pop, k: [4, 2])
    order = await get_quiz_display_order(db, user_id=student.id, item=quiz)

    payload = student_view(quiz, quiz_order=order)
    prompts = [q["prompt"] for q in payload["content"]["questions"]]
    assert prompts == ["Q4?", "Q2?"]


@pytest.mark.asyncio
async def test_student_view_serves_full_pool_when_order_is_none(db):
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _quiz_5q(db, m, random_count=None)

    payload = student_view(quiz, quiz_order=None)
    assert len(payload["content"]["questions"]) == 5
