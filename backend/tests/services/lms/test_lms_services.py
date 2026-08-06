"""LM1-2 service tests — the rules layer (services/lms).

One test per decision that could be got wrong: enrollment is idempotent and a
reactivation preserves provenance; unlock is a strict linear chain and
optional items never block it; quiz grading is server-side with threshold 0
meaning "any grade passes"; retries accumulate attempts/best without
re-completing or un-completing; completion is purely derived; and the
student-view leak test proves `is_correct` and `explanation` never reach a
student, at any depth, for every kind. Redis-free, HTTP-free.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.lms import (
    Course,
    CourseModule,
    Enrollment,
    ItemProgress,
    ModuleItem,
)
from app.models.user import User
from app.services.lms import (
    course_completion,
    enroll,
    item_progress,
    student_view,
    submit_quiz,
    unlock_state,
)
from app.services.lms.progress import COMPLETED_STATUSES


# ── factories ───────────────────────────────────────────────────────────────

async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="LMS Student",
        email=f"lms-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        roles=list(roles) if roles else ["student"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _course(db, *, author=None, **kw) -> Course:
    author = author or await _user(db, roles=["operations"])
    course = Course(
        id=uuid.uuid4(),
        title=kw.pop("title", f"Course {uuid.uuid4().hex[:8]}"),
        created_by=author.id,
        **kw,
    )
    db.add(course)
    await db.flush()
    return course


async def _module(db, course, position=1, title=None) -> CourseModule:
    module = CourseModule(
        id=uuid.uuid4(),
        course_id=course.id,
        title=title or f"Module {position}",
        position=position,
    )
    db.add(module)
    await db.flush()
    return module


async def _item(db, module, *, position, kind, **kw) -> ModuleItem:
    item = ModuleItem(
        id=uuid.uuid4(),
        module_id=module.id,
        position=position,
        kind=kind,
        **kw,
    )
    db.add(item)
    await db.flush()
    return item


def _quiz_content(threshold, questions):
    return {"pass_threshold": threshold, "questions": questions}


def _q(prompt, options, explanation="Because that is the answer."):
    return {"prompt": prompt, "explanation": explanation, "options": options}


# ── enrollment: idempotent + reactivation keeps provenance ─────────────────

@pytest.mark.asyncio
async def test_enroll_is_idempotent_and_never_rewrites_provenance(db):
    student = await _user(db)
    course = await _course(db)

    first = await enroll(db, user_id=student.id, course_id=course.id, source="self")
    second = await enroll(
        db, user_id=student.id, course_id=course.id, source="ops", program_id=uuid.uuid4()
    )

    assert second.id == first.id
    assert second.status == "active"
    # only the first path in is recorded (§2)
    assert second.source == "self"
    assert second.program_id is None

    count = (await db.execute(
        select(Enrollment).where(
            Enrollment.user_id == student.id, Enrollment.course_id == course.id
        )
    )).scalars().all()
    assert len(count) == 1


@pytest.mark.asyncio
async def test_enroll_reactivates_an_inactive_row(db):
    student = await _user(db)
    course = await _course(db)
    first = await enroll(db, user_id=student.id, course_id=course.id)

    first.status = "inactive"
    await db.flush()

    again = await enroll(db, user_id=student.id, course_id=course.id)
    assert again.id == first.id
    assert again.status == "active"


@pytest.mark.asyncio
async def test_enroll_404_for_unknown_course(db):
    student = await _user(db)
    with pytest.raises(HTTPException) as e:
        await enroll(db, user_id=student.id, course_id=uuid.uuid4())
    assert e.value.status_code == 404


# ── unlock_state: strict linear chain, optional never blocks ───────────────

async def _two_module_course(db):
    course = await _course(db)
    m1 = await _module(db, course, position=1)
    m2 = await _module(db, course, position=2)
    a = await _item(db, m1, position=1, kind="text", content={"body": "A"})
    b = await _item(db, m1, position=2, kind="text", is_required=False, content={"body": "B"})
    c = await _item(db, m2, position=1, kind="text", content={"body": "C"})
    return course, (m1, m2), (a, b, c)


@pytest.mark.asyncio
async def test_unlock_waits_for_the_previous_modules_mandatory_items(db):
    student = await _user(db)
    course, _, (a, _b, _c) = await _two_module_course(db)
    await enroll(db, user_id=student.id, course_id=course.id)

    state = await unlock_state(db, user_id=student.id, course_id=course.id)
    assert [s["position"] for s in state] == [1, 2]
    assert state[0]["locked"] is False
    assert state[1]["locked"] is True  # m1 not done yet

    # m1 has one mandatory item; completing it unlocks m2 even though the
    # optional item in m1 is still untouched.
    await item_progress(db, user_id=student.id, item_id=a.id, action="text-viewed")

    state = await unlock_state(db, user_id=student.id, course_id=course.id)
    assert state[0]["locked"] is False
    assert state[1]["locked"] is False


@pytest.mark.asyncio
async def test_a_module_with_no_mandatory_items_never_blocks(db):
    course = await _course(db)
    m1 = await _module(db, course, position=1)
    m2 = await _module(db, course, position=2)
    await _item(db, m1, position=1, kind="text", is_required=False, content={"body": "opt"})
    await _item(db, m2, position=1, kind="text", content={"body": "must"})
    student = await _user(db)
    await enroll(db, user_id=student.id, course_id=course.id)

    state = await unlock_state(db, user_id=student.id, course_id=course.id)
    assert state[0]["mandatory_total"] == 0
    assert state[0]["locked"] is False
    assert state[1]["locked"] is False


# ── item_progress: one write path, strict about kinds ──────────────────────

@pytest.mark.asyncio
async def test_item_progress_marks_viewed_items_completed(db):
    course = await _course(db)
    m = await _module(db, course)
    video = await _item(db, m, position=1, kind="video", content={})
    text = await _item(db, m, position=2, kind="text", content={"body": "hi"})
    student = await _user(db)

    await item_progress(db, user_id=student.id, item_id=video.id, action="video-watched")
    await item_progress(db, user_id=student.id, item_id=text.id, action="text-viewed")

    rows = (await db.execute(
        select(ItemProgress).where(ItemProgress.user_id == student.id)
    )).scalars().all()
    assert {r.item_id: (r.status, r.completed_at is not None) for r in rows} == {
        video.id: ("completed", True),
        text.id: ("completed", True),
    }


@pytest.mark.asyncio
async def test_quiz_cannot_be_completed_through_item_progress(db):
    """The only way a quiz turns completed is a passing submit_quiz."""
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _item(db, m, position=1, kind="quiz", content=_quiz_content(0, []))
    student = await _user(db)

    row = await item_progress(db, user_id=student.id, item_id=quiz.id, action="quiz-attempt")
    assert row.status == "in_progress"
    assert row.completed_at is None

    with pytest.raises(HTTPException) as e:
        await item_progress(db, user_id=student.id, item_id=quiz.id, action="video-watched")
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_item_progress_rejects_unknown_actions(db):
    course = await _course(db)
    m = await _module(db, course)
    text = await _item(db, m, position=1, kind="text", content={"body": "hi"})
    student = await _user(db)
    with pytest.raises(HTTPException) as e:
        await item_progress(db, user_id=student.id, item_id=text.id, action="fidget")
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_skipping_flashcards_counts_as_done(db):
    course = await _course(db)
    m = await _module(db, course)
    cards = await _item(db, m, position=1, kind="flashcards", content={"cards": []})
    student = await _user(db)

    row = await item_progress(db, user_id=student.id, item_id=cards.id, action="flashcards-skipped")
    assert row.status == "skipped"
    assert row.status in COMPLETED_STATUSES
    assert row.completed_at is not None


# ── submit_quiz: server-side grading, threshold 0 vs N ─────────────────────

@pytest.mark.asyncio
async def test_threshold_zero_means_any_grade_passes(db):
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _item(db, m, position=1, kind="quiz", content=_quiz_content(
        0,
        [_q("Is the sky up?", [{"text": "No", "is_correct": False}, {"text": "Yes", "is_correct": True}])],
    ))
    student = await _user(db)

    result = await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[0])
    assert result["passed"] is True
    assert result["score"] == 0.0
    assert result["attempts"] == 1

    row = (await db.execute(
        select(ItemProgress).where(
            ItemProgress.user_id == student.id, ItemProgress.item_id == quiz.id
        )
    )).scalars().first()
    assert row.status == "completed"


@pytest.mark.asyncio
async def test_threshold_n_grades_against_the_authored_answers(db):
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _item(db, m, position=1, kind="quiz", content=_quiz_content(
        70,
        [
            _q("2+2?", [{"text": "5", "is_correct": False}, {"text": "4", "is_correct": True}],
              explanation="Addition."),
            _q("Sky?", [{"text": "Up", "is_correct": True}, {"text": "Down", "is_correct": False}]),
        ],
    ))
    student = await _user(db)

    result = await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[1, 0])
    assert result["passed"] is True
    assert result["score"] == 100.0
    assert result["questions"][0] == {
        "prompt": "2+2?", "selected": 1, "correct": True, "explanation": "Addition.",
    }

    fail = await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[0, 1])
    # Q1 "5" (wrong), Q2 "Down" (wrong) -> 0 of 2, below threshold 70
    assert fail["passed"] is False
    assert fail["score"] == 0.0
    assert fail["questions"][0]["correct"] is False
    assert fail["questions"][0]["explanation"] == "Addition."
    assert fail["questions"][1]["correct"] is False


@pytest.mark.asyncio
async def test_quiz_rejects_malformed_answers(db):
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _item(db, m, position=1, kind="quiz", content=_quiz_content(
        0,
        [_q("Q?", [{"text": "A", "is_correct": True}])],
    ))
    student = await _user(db)

    with pytest.raises(HTTPException) as e:
        await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[])
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[3])
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_quiz_submit_rejects_non_quiz_items(db):
    course = await _course(db)
    m = await _module(db, course)
    text = await _item(db, m, position=1, kind="text", content={"body": "hi"})
    student = await _user(db)
    with pytest.raises(HTTPException) as e:
        await submit_quiz(db, user_id=student.id, item_id=text.id, answers=[])
    assert e.value.status_code == 400


# ── retries accumulate attempts/best without double-completing ─────────────

@pytest.mark.asyncio
async def test_retries_accumulate_without_double_or_undo_completion(db):
    course = await _course(db)
    m = await _module(db, course)
    quiz = await _item(db, m, position=1, kind="quiz", content=_quiz_content(
        70,
        [
            _q("Q1?", [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]),
            _q("Q2?", [{"text": "C", "is_correct": True}, {"text": "D", "is_correct": False}]),
        ],
    ))
    student = await _user(db)

    first_fail = await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[0, 1])
    # Q1 "A" (right), Q2 "D" (wrong) -> 50 of 100, below threshold 70
    assert first_fail["passed"] is False and first_fail["score"] == 50.0
    assert first_fail["attempts"] == 1 and first_fail["best_score"] == 50.0

    row = (await db.execute(
        select(ItemProgress).where(
            ItemProgress.user_id == student.id, ItemProgress.item_id == quiz.id
        )
    )).scalars().first()
    assert row.status == "in_progress"

    first_pass = await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[0, 0])
    assert first_pass["passed"] is True and first_pass["score"] == 100.0
    assert first_pass["attempts"] == 2 and first_pass["best_score"] == 100.0

    row = (await db.execute(
        select(ItemProgress).where(
            ItemProgress.user_id == student.id, ItemProgress.item_id == quiz.id
        )
    )).scalars().first()
    assert row.status == "completed"
    first_completed_at = row.completed_at

    # A later failed retry never downgrades an already-passed quiz, and a retry
    # never rewrites the first completed_at.
    fail = await submit_quiz(db, user_id=student.id, item_id=quiz.id, answers=[1, 1])
    assert fail["attempts"] == 3 and fail["passed"] is False and fail["best_score"] == 100.0
    row = (await db.execute(
        select(ItemProgress).where(
            ItemProgress.user_id == student.id, ItemProgress.item_id == quiz.id
        )
    )).scalars().first()
    assert row.status == "completed"
    assert row.completed_at == first_completed_at


# ── completion: derived, optional items never count against ────────────────

@pytest.mark.asyncio
async def test_course_completion_is_derived_from_all_modules(db):
    course = await _course(db)
    m1 = await _module(db, course, position=1)
    m2 = await _module(db, course, position=2)
    a = await _item(db, m1, position=1, kind="text", content={"body": "A"})
    opt = await _item(db, m1, position=2, kind="text", is_required=False, content={"body": "opt"})
    c = await _item(db, m2, position=1, kind="quiz", content=_quiz_content(0, []))
    student = await _user(db)

    result = await course_completion(db, user_id=student.id, course_id=course.id)
    assert result["completed"] is False
    assert [m["completed"] for m in result["modules"]] == [False, False]

    await item_progress(db, user_id=student.id, item_id=a.id, action="text-viewed")
    result = await course_completion(db, user_id=student.id, course_id=course.id)
    # the optional item in m1 is untouched, yet m1 is done
    assert result["modules"][0]["completed"] is True
    assert result["completed"] is False

    await submit_quiz(db, user_id=student.id, item_id=c.id, answers=[])
    result = await course_completion(db, user_id=student.id, course_id=course.id)
    assert result["modules"][1]["completed"] is True
    assert result["completed"] is True


# ── student_view: the answer-leakage choke point (§2) ──────────────────────

def _drill_keys(node):
    """Yield every dict key at any depth."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from _drill_keys(v)
    elif isinstance(node, list):
        for value in node:
            yield from _drill_keys(value)


@pytest.mark.asyncio
async def test_student_view_leaks_no_answers_for_any_kind(db):
    """The §2 guarantee: neither `is_correct` nor `explanation` may appear in
    the payload, at ANY depth, for every kind. A single occurrence anywhere
    — including inside an option or its siblings — fails this test."""
    course = await _course(db)
    m = await _module(db, course)

    items = [
        await _item(db, m, position=1, kind="text",
                    content={"body": "Ten minus four is six.", "explanation": "sneaky"}),
        await _item(db, m, position=2, kind="quiz", content=_quiz_content(
            70,
            [_q("Q?", [{"text": "A", "is_correct": False}, {"text": "B", "is_correct": True}],
                 explanation="Because.")],
        )),
        await _item(db, m, position=3, kind="flashcards",
                    content={"title": "T", "cards": [{"term": "Orbit", "definition": "Path."}]}),
        await _item(db, m, position=4, kind="video", content={}),
    ]

    for item in items:
        payload = student_view(item)
        for key in _drill_keys(payload):
            assert key not in {"is_correct", "explanation"}, f"{item.kind} leaked key {key}"

    # The player still gets what it needs: texts, prompts, options, thresholds,
    # timestamps, flashcard cards.
    quiz = student_view(items[1])
    assert quiz["content"]["pass_threshold"] == 70
    assert quiz["content"]["questions"][0]["options"] == [{"text": "A"}, {"text": "B"}]
    assert quiz["content"]["questions"][0]["prompt"] == "Q?"

    text = student_view(items[0])
    assert text["content"] == {"body": "Ten minus four is six."}