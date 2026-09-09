"""Cohort knowledge-quiz CRUD, attempt-taking, and grading (2026-09). See
`app/models/lms/cohort_quiz.py` for the domain overview and why it's kept
separate from `services/lms/quiz.py` (the unrelated in-course module quiz)
and `services/instructor_assessment/` (a randomized-draw sibling domain
this one's attempt/grading shape otherwise closely follows).
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.cohort_quiz import (
    CohortQuizAnswer, CohortQuizAttempt, CohortQuizQuestion, CohortQuizTemplate, CohortQuizTemplateQuestion,
)
from app.models.lms.program import LmsProgramItem
from app.schemas.lms_cohort_quiz import CohortQuizQuestionIn, CohortQuizQuestionUpdate, CohortQuizTemplateCreate, CohortQuizTemplateUpdate


# ── question bank ────────────────────────────────────────────────────────

async def create_question(
    db: AsyncSession, *, body: CohortQuizQuestionIn, created_by: uuid.UUID | None,
) -> CohortQuizQuestion:
    question = CohortQuizQuestion(
        id=uuid.uuid4(), topic=body.topic, subtopic=body.subtopic, difficulty=body.difficulty,
        time_limit_seconds=body.time_limit_seconds, bloom_level=body.bloom_level,
        question_type=body.question_type, prompt=body.prompt,
        options=[o.model_dump() for o in body.options], explanation=body.explanation,
        source_url=body.source_url, created_by=created_by,
    )
    db.add(question)
    await db.flush()
    return question


async def update_question(
    db: AsyncSession, question: CohortQuizQuestion, body: CohortQuizQuestionUpdate,
) -> CohortQuizQuestion:
    data = body.model_dump(exclude_unset=True)
    if "options" in data and data["options"] is not None:
        data["options"] = [o.model_dump() for o in body.options]
    for field, value in data.items():
        setattr(question, field, value)
    await db.flush()
    return question


async def import_questions_deduped(
    db: AsyncSession, *, parsed: list[CohortQuizQuestionIn], created_by: uuid.UUID | None,
) -> tuple[list[CohortQuizQuestion], int]:
    """Bulk-create from already-parsed import rows, skipping any whose
    prompt text already exists in the bank — the actual dedup this
    domain's importer relies on (see `cohort_quiz_importer.py`'s own
    docstring). Makes re-uploading the same source file, after fixing a
    few rows the parser flagged as errors, safe: only the new rows get
    created, nothing already in the bank is duplicated. Shared by the
    admin UI's "Import xlsx" endpoint and `scripts/
    seed_cohort_quiz_questions.py`, so there's one dedup rule to keep in
    sync, not two. Returns (created_rows, skipped_duplicate_count)."""
    existing_prompts = set((await db.execute(select(CohortQuizQuestion.prompt))).scalars().all())
    created: list[CohortQuizQuestion] = []
    skipped = 0
    for body in parsed:
        if body.prompt in existing_prompts:
            skipped += 1
            continue
        q = await create_question(db, body=body, created_by=created_by)
        existing_prompts.add(body.prompt)
        created.append(q)
    return created, skipped


async def list_questions(
    db: AsyncSession, *, topic: str | None = None, is_active: bool | None = None,
) -> list[CohortQuizQuestion]:
    q = select(CohortQuizQuestion)
    if topic:
        q = q.where(CohortQuizQuestion.topic == topic)
    if is_active is not None:
        q = q.where(CohortQuizQuestion.is_active.is_(is_active))
    return (await db.execute(q.order_by(CohortQuizQuestion.topic, CohortQuizQuestion.created_at))).scalars().all()


# ── templates ────────────────────────────────────────────────────────────

async def create_template(
    db: AsyncSession, *, body: CohortQuizTemplateCreate, created_by: uuid.UUID | None,
) -> CohortQuizTemplate:
    template = CohortQuizTemplate(id=uuid.uuid4(), name=body.name, description=body.description, created_by=created_by)
    db.add(template)
    await db.flush()
    return template


async def update_template(
    db: AsyncSession, template: CohortQuizTemplate, body: CohortQuizTemplateUpdate,
) -> CohortQuizTemplate:
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    await db.flush()
    return template


async def list_templates(db: AsyncSession) -> list[CohortQuizTemplate]:
    return (await db.execute(select(CohortQuizTemplate).order_by(CohortQuizTemplate.created_at))).scalars().all()


async def get_template_questions(db: AsyncSession, template_id: uuid.UUID) -> list[CohortQuizTemplateQuestion]:
    return (await db.execute(
        select(CohortQuizTemplateQuestion)
        .where(CohortQuizTemplateQuestion.template_id == template_id)
        .order_by(CohortQuizTemplateQuestion.position)
    )).scalars().all()


async def question_count_for_template(db: AsyncSession, template_id: uuid.UUID) -> int:
    """Active questions only — this is what a student attempt will
    actually draw (`start_attempt` below filters the same way), so the
    count shown everywhere else (the checklist badge, the template list)
    never overstates what a quiz will actually serve. The template detail
    view lists every attached row regardless of `is_active` (so a
    facilitator can see and remove a retired one), but its own summary
    count still comes from here, not `len(rows)`."""
    return await db.scalar(
        select(func.count()).select_from(CohortQuizTemplateQuestion)
        .join(CohortQuizQuestion, CohortQuizQuestion.id == CohortQuizTemplateQuestion.question_id)
        .where(CohortQuizTemplateQuestion.template_id == template_id, CohortQuizQuestion.is_active.is_(True))
    ) or 0


async def question_counts_for_templates(db: AsyncSession, template_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Batched form of `question_count_for_template` — one grouped query
    instead of N, same idiom `services/lms/program.py::items_out` already
    uses for its own per-item count."""
    if not template_ids:
        return {}
    rows = (await db.execute(
        select(CohortQuizTemplateQuestion.template_id, func.count())
        .join(CohortQuizQuestion, CohortQuizQuestion.id == CohortQuizTemplateQuestion.question_id)
        .where(CohortQuizTemplateQuestion.template_id.in_(template_ids), CohortQuizQuestion.is_active.is_(True))
        .group_by(CohortQuizTemplateQuestion.template_id)
    )).all()
    return dict(rows)


async def add_template_question(
    db: AsyncSession, *, template_id: uuid.UUID, question_id: uuid.UUID,
) -> CohortQuizTemplateQuestion:
    if await db.get(CohortQuizQuestion, question_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    exists = await db.scalar(select(CohortQuizTemplateQuestion.id).where(
        CohortQuizTemplateQuestion.template_id == template_id,
        CohortQuizTemplateQuestion.question_id == question_id,
    ))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This question is already on the template")
    max_pos = await db.scalar(
        select(func.max(CohortQuizTemplateQuestion.position)).where(CohortQuizTemplateQuestion.template_id == template_id)
    )
    row = CohortQuizTemplateQuestion(
        id=uuid.uuid4(), template_id=template_id, question_id=question_id, position=(max_pos or 0) + 1,
    )
    # The SELECT above is only a fast-path — two requests adding the same
    # question at once can both pass it before either commits. The real
    # guard is `uq_cohort_quiz_template_question_unique`; the SAVEPOINT
    # confines a lost race to this insert instead of poisoning the
    # caller's whole transaction, same pattern as
    # `start_attempt`/instructor_assessment's own get-or-create.
    try:
        async with db.begin_nested():
            db.add(row)
    except IntegrityError as e:
        if "uq_cohort_quiz_template_question_unique" not in str(e.orig):
            raise
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This question is already on the template")
    return row


async def remove_template_question(
    db: AsyncSession, *, template_id: uuid.UUID, template_question_id: uuid.UUID,
) -> None:
    row = await db.get(CohortQuizTemplateQuestion, template_question_id)
    if row is None or row.template_id != template_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found on this template")
    await db.delete(row)
    await db.flush()


async def reorder_template_questions(
    db: AsyncSession, *, template_id: uuid.UUID, template_question_ids: list[uuid.UUID],
) -> list[CohortQuizTemplateQuestion] | None:
    """Same negative-offset-then-final-position idiom as
    `services/lms/program.py::reorder_program_items` —
    `uq_cohort_quiz_template_question_position` isn't deferrable, so a
    direct swap can collide mid-transaction."""
    rows = (await db.execute(
        select(CohortQuizTemplateQuestion).where(CohortQuizTemplateQuestion.template_id == template_id)
    )).scalars().all()
    by_id = {r.id: r for r in rows}
    if set(template_question_ids) != set(by_id) or len(template_question_ids) != len(by_id):
        return None
    for offset, tq_id in enumerate(template_question_ids, start=1):
        by_id[tq_id].position = -offset
    await db.flush()
    for position, tq_id in enumerate(template_question_ids, start=1):
        by_id[tq_id].position = position
    await db.flush()
    return (await db.execute(
        select(CohortQuizTemplateQuestion)
        .where(CohortQuizTemplateQuestion.template_id == template_id)
        .order_by(CohortQuizTemplateQuestion.position)
    )).scalars().all()


# ── attempts (student-facing) ────────────────────────────────────────────

async def get_own_attempt(
    db: AsyncSession, *, program_item_id: uuid.UUID, user_id: uuid.UUID,
) -> Optional[CohortQuizAttempt]:
    return (await db.execute(
        select(CohortQuizAttempt).where(
            CohortQuizAttempt.program_item_id == program_item_id, CohortQuizAttempt.user_id == user_id,
        )
    )).scalars().first()


def _build_question_order(questions: list[CohortQuizQuestion]) -> list[dict]:
    """Shuffled presentation order, each question's own independently
    shuffled option order — `option_order[i]` is which original `options`
    index is shown at displayed position `i`. The question *set* stays the
    template's fixed list; only order and option positions are randomized
    per student, so the answer key can't be read off a shared position."""
    shuffled = list(questions)
    random.shuffle(shuffled)
    order = []
    for q in shuffled:
        idxs = list(range(len(q.options)))
        random.shuffle(idxs)
        order.append({"question_id": str(q.id), "option_order": idxs})
    return order


async def start_attempt(
    db: AsyncSession, *, item: LmsProgramItem, user_id: uuid.UUID, cohort_id: uuid.UUID | None,
) -> CohortQuizAttempt:
    """Get-or-create — a page refresh mid-attempt must never reshuffle the
    question or option order out from under the student."""
    existing = await get_own_attempt(db, program_item_id=item.id, user_id=user_id)
    if existing is not None:
        return existing

    if item.cohort_quiz_template_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No quiz is configured for this step")

    rows = (await db.execute(
        select(CohortQuizQuestion)
        .join(CohortQuizTemplateQuestion, CohortQuizTemplateQuestion.question_id == CohortQuizQuestion.id)
        .where(
            CohortQuizTemplateQuestion.template_id == item.cohort_quiz_template_id,
            CohortQuizQuestion.is_active.is_(True),
        )
    )).scalars().all()
    if not rows:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This quiz has no active questions configured")

    attempt = CohortQuizAttempt(
        id=uuid.uuid4(), program_item_id=item.id, cohort_quiz_template_id=item.cohort_quiz_template_id,
        user_id=user_id, cohort_id=cohort_id, question_order=_build_question_order(rows),
        status="in_progress", total=len(rows),
    )
    # Two tabs (or a refresh racing the first request) can both pass the
    # `existing is None` check above — the SAVEPOINT confines a lost race
    # to this insert instead of poisoning the caller's whole transaction,
    # same pattern as instructor_assessment/attempts.py::start_attempt.
    try:
        async with db.begin_nested():
            db.add(attempt)
    except IntegrityError:
        attempt = await get_own_attempt(db, program_item_id=item.id, user_id=user_id)
    return attempt


async def _resolve_question_order(
    db: AsyncSession, attempt: CohortQuizAttempt,
) -> list[tuple[dict, "CohortQuizQuestion"]]:
    """`attempt.question_order` resolved against the live `CohortQuizQuestion`
    rows, in presentation order, dropping any entry whose question was
    deactivated/removed or edited down to fewer options since the draw
    (`option_order` would then reference an out-of-range index) — skip
    rather than error. Shared by `get_attempt_questions`/`submit_attempt`/
    `get_attempt_review` so that skip condition only ever needs fixing in
    one place. A caller that needs the skipped count (`submit_attempt`,
    for shrinking `attempt.total`) computes it as
    `len(attempt.question_order) - len(resolved)`."""
    question_ids = [uuid.UUID(o["question_id"]) for o in attempt.question_order]
    rows = (await db.execute(
        select(CohortQuizQuestion).where(CohortQuizQuestion.id.in_(question_ids))
    )).scalars().all()
    by_id = {q.id: q for q in rows}

    resolved = []
    for entry in attempt.question_order:
        q = by_id.get(uuid.UUID(entry["question_id"]))
        option_order: list[int] = entry["option_order"]
        if q is None or max(option_order, default=-1) >= len(q.options):
            continue
        resolved.append((entry, q))
    return resolved


async def get_attempt_questions(db: AsyncSession, attempt: CohortQuizAttempt) -> list[dict]:
    """The attempt's questions for display — presentation order, options in
    the persisted shuffled order, `is_correct` never included."""
    resolved = await _resolve_question_order(db, attempt)
    out = []
    for entry, q in resolved:
        option_order: list[int] = entry["option_order"]
        out.append({
            "question_id": q.id, "topic": q.topic, "difficulty": q.difficulty,
            "time_limit_seconds": q.time_limit_seconds, "prompt": q.prompt,
            "options": [q.options[i]["text"] for i in option_order],
        })
    return out


async def submit_attempt(db: AsyncSession, attempt: CohortQuizAttempt, answers: list) -> CohortQuizAttempt:
    """`answers` is a list of `CohortQuizAnswerIn` — all at once, not
    per-question (same shape as instructor_assessment's `submit_attempt`).
    Grades against the persisted `question_order` only — never trusts a
    client-supplied "is_correct", and the per-question elapsed time is
    recorded for analytics only, never re-validated server-side."""
    if attempt.status == "submitted":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This quiz is already submitted")

    resolved = await _resolve_question_order(db, attempt)
    answers_by_qid = {str(a.question_id): a for a in answers}

    score = 0
    topic_breakdown: dict[str, dict[str, int]] = {}

    # The question was removed, or edited down to fewer options, between
    # start and submit — shrink `total` to match so the result screen's
    # "score / total" never counts a question that was never actually
    # served (see `_resolve_question_order`'s own docstring).
    skipped = len(attempt.question_order) - len(resolved)
    for entry, q in resolved:
        qid = q.id
        option_order: list[int] = entry["option_order"]
        answer = answers_by_qid.get(str(qid))
        selected_position = answer.selected_option_index if answer else None
        selected_original_index = (
            option_order[selected_position]
            if selected_position is not None and 0 <= selected_position < len(option_order)
            else None
        )
        is_correct = selected_original_index is not None and bool(q.options[selected_original_index].get("is_correct"))

        if is_correct:
            score += 1
        bucket = topic_breakdown.setdefault(q.topic, {"correct": 0, "total": 0})
        bucket["total"] += 1
        if is_correct:
            bucket["correct"] += 1

        db.add(CohortQuizAnswer(
            id=uuid.uuid4(), attempt_id=attempt.id, question_id=qid, topic=q.topic,
            selected_option_index=selected_original_index, is_correct=is_correct,
            timed_out=bool(answer.timed_out) if answer else True,
            time_taken_seconds=answer.time_taken_seconds if answer else None,
        ))

    attempt.status = "submitted"
    attempt.score = score
    attempt.total -= skipped
    attempt.topic_breakdown = topic_breakdown
    attempt.submitted_at = datetime.now(timezone.utc)
    await db.flush()
    return attempt


async def get_attempt_review(db: AsyncSession, attempt: CohortQuizAttempt) -> list[dict]:
    """Per-question review — correct answer + explanation revealed
    alongside each question. Only call this on an already-`submitted`
    attempt — same reasoning as instructor_assessment's own
    `get_attempt_review`."""
    resolved = await _resolve_question_order(db, attempt)

    answers = (await db.execute(
        select(CohortQuizAnswer).where(CohortQuizAnswer.attempt_id == attempt.id)
    )).scalars().all()
    answers_by_qid = {a.question_id: a for a in answers}

    out = []
    for entry, q in resolved:
        answer = answers_by_qid.get(q.id)
        if answer is None:
            # No persisted CohortQuizAnswer means this question was skipped
            # at submit time (invalid then — see `_resolve_question_order`)
            # and `attempt.total`/`score` were adjusted accordingly. Even
            # if the question was since edited back into a valid shape,
            # it must stay excluded here too, or the review list would grow
            # past what `total`/`score` at the top of the result screen say.
            continue
        option_order: list[int] = entry["option_order"]
        correct_original_index = next(i for i, o in enumerate(q.options) if o.get("is_correct"))
        out.append({
            "question_id": q.id, "topic": q.topic, "prompt": q.prompt,
            "options": [q.options[i]["text"] for i in option_order],
            "selected_index": option_order.index(answer.selected_option_index)
            if answer.selected_option_index is not None else None,
            "correct_index": option_order.index(correct_original_index),
            "is_correct": answer.is_correct,
            "explanation": q.explanation,
        })
    return out


# ── strengths & weaknesses (read-only, derived) ─────────────────────────

async def get_student_topic_breakdown(db: AsyncSession, user_id: uuid.UUID) -> dict[str, dict[str, int]]:
    """Live cross-attempt aggregation — never cached, same posture as
    `services/instructor_assessment/performance.py::get_performance`."""
    attempts = (await db.execute(
        select(CohortQuizAttempt).where(CohortQuizAttempt.user_id == user_id, CohortQuizAttempt.status == "submitted")
    )).scalars().all()
    breakdown: dict[str, dict[str, int]] = {}
    for attempt in attempts:
        for topic, counts in (attempt.topic_breakdown or {}).items():
            bucket = breakdown.setdefault(topic, {"correct": 0, "total": 0})
            bucket["correct"] += counts.get("correct", 0)
            bucket["total"] += counts.get("total", 0)
    return breakdown
