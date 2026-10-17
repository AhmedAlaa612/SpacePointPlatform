"""Cohort knowledge-quiz service (2026-09) — bank/template CRUD, get-or-create
attempt semantics, grading correctness, and cross-attempt topic breakdown."""

import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.lms.cohort_quiz import CohortQuizAttempt, CohortQuizQuestion
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User
from app.schemas.lms_cohort_quiz import (
    CohortQuizQuestionIn,
    CohortQuizQuestionOptionIn,
    CohortQuizQuestionUpdate,
    CohortQuizTemplateCreate,
)
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
async def test_generate_template_questions_replaces_the_existing_set_with_a_spread_across_topics(db):
    user = await _make_user(db)
    # A hand-picked question already on the template — generate must
    # replace the *row*, not add to it. (Its underlying question is still
    # a valid active candidate, so asserting it can't be re-drawn by
    # question_id would be flaky — round-robin can legitimately pick it
    # again. What must hold deterministically is that the old
    # CohortQuizTemplateQuestion row is gone, replaced by a fresh one.)
    template, _existing = await _make_template_with_questions(db, user=user, topics=["EPS"])
    old_row_ids = {r.id for r in await svc.get_template_questions(db, template.id)}

    for topic in ["EPS", "ADCS", "CDHS"]:
        for _ in range(3):
            await svc.create_question(db, body=_question_body(topic), created_by=user.id)

    rows = await svc.generate_template_questions(db, template_id=template.id, count=6)

    assert len(rows) == 6
    positions = [r.position for r in rows]
    assert positions == list(range(1, 7))
    new_row_ids = {r.id for r in rows}
    assert old_row_ids.isdisjoint(new_row_ids)  # the old row was deleted, not reused

    generated_questions = (await db.execute(
        select(CohortQuizQuestion).where(CohortQuizQuestion.id.in_({r.question_id for r in rows}))
    )).scalars().all()
    topics_drawn = {q.topic for q in generated_questions}
    assert len(topics_drawn) >= 2  # round-robin spreads across topics, not all from one


@pytest.mark.asyncio
async def test_generate_template_questions_respects_a_topic_filter(db):
    user = await _make_user(db)
    template = await svc.create_template(db, body=CohortQuizTemplateCreate(name="Filtered"), created_by=user.id)
    for topic in ["EPS", "ADCS"]:
        for _ in range(2):
            await svc.create_question(db, body=_question_body(topic), created_by=user.id)

    rows = await svc.generate_template_questions(db, template_id=template.id, count=10, topics=["EPS"])

    assert len(rows) == 2  # only 2 EPS questions exist — draws what's there, doesn't error
    generated_questions = (await db.execute(
        select(CohortQuizQuestion).where(CohortQuizQuestion.id.in_([r.question_id for r in rows]))
    )).scalars().all()
    assert all(q.topic == "EPS" for q in generated_questions)


@pytest.mark.asyncio
async def test_generate_template_questions_only_draws_active_questions(db):
    user = await _make_user(db)
    template, questions = await _make_template_with_questions(db, user=user, topics=["EPS"])
    inactive = await svc.create_question(db, body=_question_body("EPS"), created_by=user.id)
    inactive.is_active = False
    await db.flush()

    rows = await svc.generate_template_questions(db, template_id=template.id, count=5)

    assert inactive.id not in {r.question_id for r in rows}


@pytest.mark.asyncio
async def test_generate_template_questions_rejects_a_topic_filter_matching_nothing_without_wiping_the_template(db):
    """A typo'd or all-retired topic filter must not delete the existing
    set for zero replacement — the guard has to run before any deletes."""
    user = await _make_user(db)
    template, existing = await _make_template_with_questions(db, user=user, topics=["EPS"])

    with pytest.raises(HTTPException) as exc:
        await svc.generate_template_questions(db, template_id=template.id, count=5, topics=["Nonexistent Topic"])
    assert exc.value.status_code == 409

    surviving = await svc.get_template_questions(db, template.id)
    assert [r.question_id for r in surviving] == [existing[0].id]  # untouched


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


@pytest.mark.asyncio
async def test_update_question_rejects_option_changes_while_an_attempt_has_it_in_progress(db):
    """Grading and review both read `CohortQuizQuestion.options` live (only
    presentation order is frozen at start time) — changing options out from
    under a student mid-quiz would silently regrade against content they
    never saw."""
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program 9")
    db.add(lms_program)
    await db.flush()
    template, questions = await _make_template_with_questions(db, user=user, topics=["EPS"])
    item = await _quiz_item(db, lms_program=lms_program, template_id=template.id)
    student = await _make_user(db, roles=["student"])

    await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)

    with pytest.raises(HTTPException) as exc:
        await svc.update_question(
            db, questions[0],
            CohortQuizQuestionUpdate(options=[
                CohortQuizQuestionOptionIn(text="A", is_correct=True),
                CohortQuizQuestionOptionIn(text="B", is_correct=False),
            ]),
        )
    assert exc.value.status_code == 409

    # Non-option fields are untouched by the guard.
    updated = await svc.update_question(db, questions[0], CohortQuizQuestionUpdate(subtopic="Renamed"))
    assert updated.subtopic == "Renamed"


@pytest.mark.asyncio
async def test_update_question_allows_option_changes_once_no_attempt_is_in_progress(db):
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program 10")
    db.add(lms_program)
    await db.flush()
    template, questions = await _make_template_with_questions(db, user=user, topics=["EPS"])
    item = await _quiz_item(db, lms_program=lms_program, template_id=template.id)
    student = await _make_user(db, roles=["student"])

    attempt = await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)
    await svc.submit_attempt(db, attempt, [])

    updated = await svc.update_question(
        db, questions[0],
        CohortQuizQuestionUpdate(options=[
            CohortQuizQuestionOptionIn(text="X", is_correct=True),
            CohortQuizQuestionOptionIn(text="Y", is_correct=False),
        ]),
    )
    assert [o["text"] for o in updated.options] == ["X", "Y"]


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
    await svc.submit_attempt(db, attempt, [
        _Answer(uuid.UUID(entry["question_id"]), wrong_position, time_taken_seconds=7),
    ])

    review = await svc.get_attempt_review(db, attempt)
    assert review[0]["is_correct"] is False
    assert review[0]["explanation"] == "A is correct because of reasons."
    assert review[0]["selected_index"] == wrong_position
    assert review[0]["correct_index"] != wrong_position
    assert review[0]["time_taken_seconds"] == 7
    assert review[0]["timed_out"] is False


@pytest.mark.asyncio
async def test_get_attempt_review_flags_a_timed_out_question_as_unanswered(db):
    """`selected_index` alone already means "left unanswered" — `timed_out`
    just distinguishes *why*, for the ops/instructor review (vs. some
    hypothetical future explicit skip)."""
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program 11")
    db.add(lms_program)
    await db.flush()
    template, _ = await _make_template_with_questions(db, user=user, topics=["EPS"])
    item = await _quiz_item(db, lms_program=lms_program, template_id=template.id)
    student = await _make_user(db, roles=["student"])

    attempt = await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)
    entry = attempt.question_order[0]
    await svc.submit_attempt(db, attempt, [
        _Answer(uuid.UUID(entry["question_id"]), None, timed_out=True, time_taken_seconds=15),
    ])

    review = await svc.get_attempt_review(db, attempt)
    assert review[0]["selected_index"] is None
    assert review[0]["timed_out"] is True
    assert review[0]["time_taken_seconds"] == 15


# ── ops/instructor reset ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reset_attempt_deletes_it_so_the_next_start_is_brand_new(db):
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program 12")
    db.add(lms_program)
    await db.flush()
    template, _ = await _make_template_with_questions(db, user=user, topics=["EPS"])
    item = await _quiz_item(db, lms_program=lms_program, template_id=template.id)
    student = await _make_user(db, roles=["student"])

    first = await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)
    await svc.submit_attempt(db, first, [])

    deleted = await svc.reset_attempt(db, program_item_id=item.id, user_id=student.id)
    assert deleted is True
    assert await svc.get_own_attempt(db, program_item_id=item.id, user_id=student.id) is None

    second = await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)
    assert second.id != first.id
    assert second.status == "in_progress"


@pytest.mark.asyncio
async def test_reset_attempt_on_a_student_who_never_started_is_a_noop(db):
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program 13")
    db.add(lms_program)
    await db.flush()
    template, _ = await _make_template_with_questions(db, user=user, topics=["EPS"])
    item = await _quiz_item(db, lms_program=lms_program, template_id=template.id)
    student = await _make_user(db, roles=["student"])

    deleted = await svc.reset_attempt(db, program_item_id=item.id, user_id=student.id)
    assert deleted is False


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


@pytest.mark.asyncio
async def test_create_textarea_question_and_opinion_question():
    # 1. Textarea question (options can be empty)
    q_text = CohortQuizQuestionIn(
        topic="Reflections", difficulty="Easy", time_limit_seconds=60,
        question_type="textarea", prompt="Describe what you learned today",
        options=[],
    )
    assert q_text.question_type == "textarea"
    assert q_text.options == []

    # 2. Opinion-based MCQ (no correct answer marked)
    q_opinion = CohortQuizQuestionIn(
        topic="Survey", difficulty="Easy", time_limit_seconds=30,
        question_type="mcq", prompt="Which track interests you most?",
        options=[
            CohortQuizQuestionOptionIn(text="Hardware", is_correct=False),
            CohortQuizQuestionOptionIn(text="Software", is_correct=False),
        ],
    )
    assert q_opinion.question_type == "mcq"
    assert all(not o.is_correct for o in q_opinion.options)

    # 3. Reject more than one correct option
    with pytest.raises(ValueError):
        CohortQuizQuestionIn(
            topic="Test", difficulty="Easy", time_limit_seconds=15, prompt="Bad",
            options=[
                CohortQuizQuestionOptionIn(text="A", is_correct=True),
                CohortQuizQuestionOptionIn(text="B", is_correct=True),
            ],
        )


@pytest.mark.asyncio
async def test_submit_attempt_with_textarea_and_opinion_questions(db):
    user = await _make_user(db)
    cohort = await _make_cohort(db)
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=cohort.program_id, name="Quiz Program Mixed")
    db.add(lms_program)
    await db.flush()

    template = await svc.create_template(db, body=CohortQuizTemplateCreate(name="Mixed Template"), created_by=user.id)

    # 1. Graded MCQ
    q_graded = await svc.create_question(db, body=_question_body("GradedTopic", correct_letter="A"), created_by=user.id)
    await svc.add_template_question(db, template_id=template.id, question_id=q_graded.id)

    # 2. Opinion MCQ
    q_opinion = await svc.create_question(db, body=CohortQuizQuestionIn(
        topic="OpinionTopic", difficulty="Easy", time_limit_seconds=20,
        question_type="mcq", prompt="Which subsystem is coolest?",
        options=[
            CohortQuizQuestionOptionIn(text="Payload", is_correct=False),
            CohortQuizQuestionOptionIn(text="Power", is_correct=False),
        ],
    ), created_by=user.id)
    await svc.add_template_question(db, template_id=template.id, question_id=q_opinion.id)

    # 3. Textarea Question
    q_textarea = await svc.create_question(db, body=CohortQuizQuestionIn(
        topic="ReflectionTopic", difficulty="Medium", time_limit_seconds=45,
        question_type="textarea", prompt="Write your thoughts on orbital mechanics",
        options=[],
    ), created_by=user.id)
    await svc.add_template_question(db, template_id=template.id, question_id=q_textarea.id)

    item = await _quiz_item(db, lms_program=lms_program, template_id=template.id)
    student = await _make_user(db, roles=["student"])

    attempt = await svc.start_attempt(db, item=item, user_id=student.id, cohort_id=cohort.id)
    questions = await svc.get_attempt_questions(db, attempt)
    assert len(questions) == 3

    text_q = next(q for q in questions if q["question_id"] == q_textarea.id)
    assert text_q["question_type"] == "textarea"
    assert text_q["options"] == []

    # Student submits answers
    class _AnswerInput:
        def __init__(self, qid, selected=None, text=None, timed_out=False):
            self.question_id = qid
            self.selected_option_index = selected
            self.text_answer = text
            self.timed_out = timed_out
            self.time_taken_seconds = 5

    # Find position of correct option for graded question
    order_graded = next(e for e in attempt.question_order if e["question_id"] == str(q_graded.id))
    correct_pos = order_graded["option_order"].index(0)

    sub_answers = [
        _AnswerInput(q_graded.id, selected=correct_pos),
        _AnswerInput(q_opinion.id, selected=0),
        _AnswerInput(q_textarea.id, text="Orbital mechanics requires careful delta-v planning."),
    ]
    submitted_attempt = await svc.submit_attempt(db, attempt, sub_answers)

    # Only graded question counts toward score and total
    assert submitted_attempt.score == 1
    assert submitted_attempt.total == 1
    assert "GradedTopic" in submitted_attempt.topic_breakdown
    assert submitted_attempt.topic_breakdown["GradedTopic"] == {"correct": 1, "total": 1}
    assert "OpinionTopic" not in submitted_attempt.topic_breakdown
    assert "ReflectionTopic" not in submitted_attempt.topic_breakdown

    # Review checks
    review = await svc.get_attempt_review(db, submitted_attempt)
    assert len(review) == 3

    rev_graded = next(r for r in review if r["question_id"] == q_graded.id)
    assert rev_graded["is_correct"] is True
    assert rev_graded["correct_index"] is not None

    rev_opinion = next(r for r in review if r["question_id"] == q_opinion.id)
    assert rev_opinion["is_correct"] is None
    assert rev_opinion["correct_index"] is None
    assert rev_opinion["selected_index"] is not None

    rev_text = next(r for r in review if r["question_id"] == q_textarea.id)
    assert rev_text["is_correct"] is None
    assert rev_text["question_type"] == "textarea"
    assert rev_text["text_answer"] == "Orbital mechanics requires careful delta-v planning."

