"""Cohort knowledge-quiz service (2026-09) — bank/template CRUD, get-or-create
attempt semantics, grading correctness, and cross-attempt topic breakdown."""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.lms.cohort_quiz import CohortQuizAttempt
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User
from app.schemas.lms_cohort_quiz import CohortQuizQuestionIn, CohortQuizQuestionOptionIn, CohortQuizTemplateCreate
from app.services.lms import cohort_quiz as svc


async def _make_user(db, **overrides) -> User:
    defaults = dict(
        id=uuid.uuid4(), full_name="Test Facilitator", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=["facilitator"],
    )
    defaults.update(overrides)
    user = User(**defaults)
    db.add(user)
    await db.flush()
    return user


async def _make_cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"CQ-{uuid.uuid4().hex[:8]}", name="Cohort Quiz Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Cohort Quiz Test Cohort", status="running")
    db.add(cohort)
    await db.flush()
    return cohort


def _question_body(topic: str, correct_letter: str = "A") -> CohortQuizQuestionIn:
    letters = "ABCD"
    return CohortQuizQuestionIn(
        topic=topic, difficulty="Easy", time_limit_seconds=15, prompt=f"{topic} question {uuid.uuid4().hex[:6]}",
        options=[CohortQuizQuestionOptionIn(text=letter, is_correct=letter == correct_letter) for letter in letters],
    )


async def _make_template_with_questions(db, *, user, topics: list[str]) -> tuple:
    template = await svc.create_template(db, body=CohortQuizTemplateCreate(name="Test Template"), created_by=user.id)
    questions = []
    for topic in topics:
        q = await svc.create_question(db, body=_question_body(topic), created_by=user.id)
        await svc.add_template_question(db, template_id=template.id, question_id=q.id)
        questions.append(q)
    return template, questions


async def _quiz_item(db, *, lms_program: LmsProgram, template_id: uuid.UUID) -> LmsProgramItem:
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="quiz", title="Knowledge check", cohort_quiz_template_id=template_id,
    )
    db.add(item)
    await db.flush()
    return item


# ── question bank / template CRUD ───────────────────────────────────────

@pytest.mark.asyncio
async def test_create_question_rejects_more_than_one_correct_option():
    with pytest.raises(ValueError):
        CohortQuizQuestionIn(
            topic="EPS", difficulty="Easy", time_limit_seconds=15, prompt="Bad question",
            options=[
                CohortQuizQuestionOptionIn(text="A", is_correct=True),
                CohortQuizQuestionOptionIn(text="B", is_correct=True),
            ],
        )


@pytest.mark.asyncio
async def test_import_questions_deduped_skips_prompts_already_in_the_bank(db):
    """Re-uploading the same source file (a realistic workflow: fix a few
    error rows, re-upload the whole sheet) must not duplicate every
    already-imported question."""
    user = await _make_user(db)
    first_batch = [_question_body("EPS", correct_letter="A"), _question_body("ADCS", correct_letter="B")]
    created, skipped = await svc.import_questions_deduped(db, parsed=first_batch, created_by=user.id)
    assert len(created) == 2
    assert skipped == 0

    # Re-run with the same two rows plus one genuinely new one.
    third = _question_body("CDHS", correct_letter="C")
    second_batch = [first_batch[0], first_batch[1], third]
    created_again, skipped_again = await svc.import_questions_deduped(db, parsed=second_batch, created_by=user.id)
    assert len(created_again) == 1
    assert created_again[0].prompt == third.prompt
    assert skipped_again == 2


@pytest.mark.asyncio
async def test_add_template_question_rejects_duplicates(db):
    user = await _make_user(db)
    template, questions = await _make_template_with_questions(db, user=user, topics=["EPS"])
    with pytest.raises(HTTPException) as exc:
        await svc.add_template_question(db, template_id=template.id, question_id=questions[0].id)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_template_question_unique_constraint_backstops_a_lost_race(db):
    """The service's own pre-check (test above) is only a fast path — this
    proves the real guard, `uq_cohort_quiz_template_question_unique`, by
    inserting a duplicate directly (bypassing the pre-check entirely, the
    same way a second concurrent request that raced past it would)."""
    from app.models.lms.cohort_quiz import CohortQuizTemplateQuestion

    user = await _make_user(db)
    template, questions = await _make_template_with_questions(db, user=user, topics=["EPS"])
    with pytest.raises(IntegrityError):
        db.add(CohortQuizTemplateQuestion(
            id=uuid.uuid4(), template_id=template.id, question_id=questions[0].id, position=99,
        ))
        await db.flush()


@pytest.mark.asyncio
async def test_reorder_template_questions_rejects_a_mismatched_set(db):
    user = await _make_user(db)
    template, questions = await _make_template_with_questions(db, user=user, topics=["EPS", "ADCS"])
    result = await svc.reorder_template_questions(db, template_id=template.id, template_question_ids=[uuid.uuid4()])
    assert result is None


@pytest.mark.asyncio
async def test_question_count_for_template_only_counts_active_questions(db):
    """The count must match what start_attempt will actually draw — never
    overstate a quiz that's had questions retired out from under it."""
    user = await _make_user(db)
    template, questions = await _make_template_with_questions(db, user=user, topics=["EPS", "ADCS", "CDHS"])
    assert await svc.question_count_for_template(db, template.id) == 3

    questions[0].is_active = False
    await db.flush()
    assert await svc.question_count_for_template(db, template.id) == 2

    counts = await svc.question_counts_for_templates(db, [template.id])
    assert counts[template.id] == 2


# ── get-or-create attempt semantics ──────────────────────────────────────

@pytest.mark.asyncio
async def test_start_attempt_requires_a_configured_template(db):
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Unconfigured")
    db.add(lms_program)
    await db.flush()
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="quiz", title="No template",
    )
    db.add(item)
    await db.flush()

    with pytest.raises(HTTPException) as exc:
        await svc.start_attempt(db, item=item, user_id=user.id, cohort_id=cohort.id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_start_attempt_is_get_or_create(db):
    """A page refresh mid-attempt must never reshuffle the question or
    option order."""
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program")
    db.add(lms_program)
    await db.flush()
    template, questions = await _make_template_with_questions(db, user=user, topics=["EPS", "ADCS", "CDHS"])
    item = await _quiz_item(db, lms_program=lms_program, template_id=template.id)
    student = await _make_user(db, roles=["student"])

    first = await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)
    second = await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)

    assert first.id == second.id
    assert first.question_order == second.question_order
    assert first.total == len(questions)

    count = await db.scalar(
        select(CohortQuizAttempt).where(
            CohortQuizAttempt.program_item_id == item.id, CohortQuizAttempt.user_id == student.id,
        )
    )
    assert count is not None


@pytest.mark.asyncio
async def test_start_attempt_only_draws_active_questions(db):
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program 2")
    db.add(lms_program)
    await db.flush()
    template, questions = await _make_template_with_questions(db, user=user, topics=["EPS", "ADCS"])
    questions[0].is_active = False
    await db.flush()
    item = await _quiz_item(db, lms_program=lms_program, template_id=template.id)
    student = await _make_user(db, roles=["student"])

    attempt = await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)
    assert attempt.total == 1


# ── grading ───────────────────────────────────────────────────────────────

class _Answer:
    def __init__(self, question_id, selected_option_index, timed_out=False, time_taken_seconds=None):
        self.question_id = question_id
        self.selected_option_index = selected_option_index
        self.timed_out = timed_out
        self.time_taken_seconds = time_taken_seconds


@pytest.mark.asyncio
async def test_submit_attempt_grades_against_shuffled_option_order_and_builds_topic_breakdown(db):
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program 3")
    db.add(lms_program)
    await db.flush()
    template, questions = await _make_template_with_questions(db, user=user, topics=["EPS", "EPS", "ADCS"])
    item = await _quiz_item(db, lms_program=lms_program, template_id=template.id)
    student = await _make_user(db, roles=["student"])

    attempt = await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)

    # Answer every question correctly (option "A", the correct one, is at
    # whichever displayed position option_order maps index 0 to).
    answers = [
        _Answer(uuid.UUID(entry["question_id"]), entry["option_order"].index(0), time_taken_seconds=5)
        for entry in attempt.question_order
    ]
    result = await svc.submit_attempt(db, attempt, answers)

    assert result.status == "submitted"
    assert result.score == 3
    assert result.topic_breakdown["EPS"] == {"correct": 2, "total": 2}
    assert result.topic_breakdown["ADCS"] == {"correct": 1, "total": 1}


@pytest.mark.asyncio
async def test_submit_attempt_treats_a_blank_answer_as_wrong(db):
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program 4")
    db.add(lms_program)
    await db.flush()
    template, _ = await _make_template_with_questions(db, user=user, topics=["EPS"])
    item = await _quiz_item(db, lms_program=lms_program, template_id=template.id)
    student = await _make_user(db, roles=["student"])

    attempt = await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)
    result = await svc.submit_attempt(db, attempt, [
        _Answer(uuid.UUID(attempt.question_order[0]["question_id"]), None, timed_out=True),
    ])

    assert result.score == 0
    assert result.topic_breakdown["EPS"] == {"correct": 0, "total": 1}


@pytest.mark.asyncio
async def test_submit_attempt_twice_is_rejected(db):
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program 5")
    db.add(lms_program)
    await db.flush()
    template, _ = await _make_template_with_questions(db, user=user, topics=["EPS"])
    item = await _quiz_item(db, lms_program=lms_program, template_id=template.id)
    student = await _make_user(db, roles=["student"])

    attempt = await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)
    await svc.submit_attempt(db, attempt, [])

    with pytest.raises(HTTPException) as exc:
        await svc.submit_attempt(db, attempt, [])
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_submit_attempt_shrinks_total_when_a_question_is_edited_down_mid_attempt(db):
    """A question edited to fewer options between start and submit is
    skipped during grading (its persisted option_order goes out of range) —
    `total` must shrink to match, so the result screen's "score / total"
    never counts a question that was never actually served."""
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program 8")
    db.add(lms_program)
    await db.flush()
    template, questions = await _make_template_with_questions(db, user=user, topics=["EPS", "ADCS"])
    item = await _quiz_item(db, lms_program=lms_program, template_id=template.id)
    student = await _make_user(db, roles=["student"])

    attempt = await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)
    assert attempt.total == 2

    # Shrink one question's options from 4 down to 1 — any option_order
    # persisted at start time now has indices out of range for it.
    questions[0].options = [questions[0].options[0]]
    await db.flush()

    surviving_entry = next(
        e for e in attempt.question_order if uuid.UUID(e["question_id"]) != questions[0].id
    )
    answers = [_Answer(uuid.UUID(surviving_entry["question_id"]), surviving_entry["option_order"].index(0))]
    result = await svc.submit_attempt(db, attempt, answers)

    assert result.total == 1
    assert result.score == 1

    # Restoring the question afterward must not resurrect it in the review
    # — the review list must always match `total`/`score`, not whatever
    # the question's live shape happens to be when reviewed.
    questions[0].options = [
        {"text": "A", "is_correct": True}, {"text": "B", "is_correct": False},
        {"text": "C", "is_correct": False}, {"text": "D", "is_correct": False},
    ]
    await db.flush()
    review = await svc.get_attempt_review(db, result)
    assert len(review) == 1


@pytest.mark.asyncio
async def test_get_attempt_review_reveals_correct_answer_and_explanation(db):
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program 6")
    db.add(lms_program)
    await db.flush()
    template = await svc.create_template(db, body=CohortQuizTemplateCreate(name="Review Template"), created_by=user.id)
    q = await svc.create_question(
        db, body=CohortQuizQuestionIn(
            topic="EPS", difficulty="Easy", time_limit_seconds=15, prompt="Explained question",
            options=[
                CohortQuizQuestionOptionIn(text="A", is_correct=True),
                CohortQuizQuestionOptionIn(text="B", is_correct=False),
            ],
            explanation="A is correct because of reasons.",
        ),
        created_by=user.id,
    )
    await svc.add_template_question(db, template_id=template.id, question_id=q.id)
    item = await _quiz_item(db, lms_program=lms_program, template_id=template.id)
    student = await _make_user(db, roles=["student"])

    attempt = await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)
    entry = attempt.question_order[0]
    wrong_position = 1 - entry["option_order"].index(0)
    await svc.submit_attempt(db, attempt, [_Answer(uuid.UUID(entry["question_id"]), wrong_position)])

    review = await svc.get_attempt_review(db, attempt)
    assert review[0]["is_correct"] is False
    assert review[0]["explanation"] == "A is correct because of reasons."
    assert review[0]["selected_index"] == wrong_position
    assert review[0]["correct_index"] != wrong_position


# ── strengths & weaknesses ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_student_topic_breakdown_sums_across_submitted_attempts(db):
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program 7")
    db.add(lms_program)
    await db.flush()
    student = await _make_user(db, roles=["student"])

    template_a, _ = await _make_template_with_questions(db, user=user, topics=["EPS"])
    item_a = await _quiz_item(db, lms_program=lms_program, template_id=template_a.id)
    attempt_a = await svc.start_attempt(db, item=item_a, user_id=student.id, cohort_id=cohort.id)
    await svc.submit_attempt(db, attempt_a, [
        _Answer(uuid.UUID(attempt_a.question_order[0]["question_id"]), attempt_a.question_order[0]["option_order"].index(0)),
    ])

    template_b, _ = await _make_template_with_questions(db, user=user, topics=["EPS", "ADCS"])
    item_b = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=2,
        item_type="quiz", title="Second quiz", cohort_quiz_template_id=template_b.id,
    )
    db.add(item_b)
    await db.flush()
    attempt_b = await svc.start_attempt(db, item=item_b, user_id=student.id, cohort_id=cohort.id)
    await svc.submit_attempt(db, attempt_b, [])  # every question left blank

    breakdown = await svc.get_student_topic_breakdown(db, student.id)
    assert breakdown["EPS"] == {"correct": 1, "total": 2}
    assert breakdown["ADCS"] == {"correct": 0, "total": 1}
