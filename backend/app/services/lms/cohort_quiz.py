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
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.cohort_quiz import (
    CohortQuizAnswer, CohortQuizAttempt, CohortQuizQuestion, CohortQuizTemplate, CohortQuizTemplateQuestion,
)
from app.models.lms.program import LmsProgramItem
from app.schemas.lms_cohort_quiz import (
    CohortQuizQuestionIn, CohortQuizQuestionReviewOut, CohortQuizQuestionUpdate, CohortQuizResultOut,
    CohortQuizTemplateCreate, CohortQuizTemplateUpdate,
)


# ── question bank ────────────────────────────────────────────────────────

async def create_question(
    db: AsyncSession, *, body: CohortQuizQuestionIn, created_by: uuid.UUID | None,
) -> CohortQuizQuestion:
    question = CohortQuizQuestion(
        id=uuid.uuid4(), topic=body.topic, subtopic=body.subtopic, difficulty=body.difficulty,
        time_limit_seconds=body.time_limit_seconds, bloom_level=body.bloom_level,
        question_type=body.question_type or "mcq", is_optional=bool(body.is_optional), prompt=body.prompt,
        options=[o.model_dump() for o in body.options], explanation=body.explanation,
        source_url=body.source_url, created_by=created_by,
    )
    db.add(question)
    await db.flush()
    return question


async def _question_in_an_in_progress_attempt(db: AsyncSession, question_id: uuid.UUID) -> bool:
    """Whether any not-yet-submitted attempt has already drawn this
    question — grading and review both read `CohortQuizQuestion.options`
    live (only presentation order is frozen in `question_order`), so
    changing which option is correct — or the options themselves — while
    a student is mid-quiz would silently regrade their answer against
    content they never actually saw."""
    orders = (await db.execute(
        select(CohortQuizAttempt.question_order).where(CohortQuizAttempt.status == "in_progress")
    )).scalars().all()
    qid = str(question_id)
    return any(entry.get("question_id") == qid for order in orders for entry in order)


async def update_question(
    db: AsyncSession, question: CohortQuizQuestion, body: CohortQuizQuestionUpdate,
) -> CohortQuizQuestion:
    data = body.model_dump(exclude_unset=True)
    if "options" in data and data["options"] is not None:
        if await _question_in_an_in_progress_attempt(db, question.id):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="A student has this question open in an in-progress quiz attempt right now — "
                       "its options can't be changed until they submit (or you can wait and retry).",
            )
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


async def generate_template_questions(
    db: AsyncSession, *, template_id: uuid.UUID, count: int, topics: list[str] | None = None,
) -> list[CohortQuizTemplateQuestion]:
    """Bulk auto-populate a template's fixed question set — replaces
    whatever's currently on it. A facilitator-authoring convenience (a fast
    starting point instead of hand-picking one question at a time), not a
    per-student draw: the template's set is still fixed once generated,
    same "identical set for every student" rule this domain always
    follows (see this module's own docstring). "Regenerate" in the admin
    UI is just calling this again for a different random pick.

    Round-robins across topics for spread rather than pure random (a flat
    random draw could plausibly land entirely in one topic) — same idiom
    `services/instructor_assessment/attempts.py::_round_robin_draw` uses,
    simplified (no critical-floor tier here). Only draws from active
    questions, same as `start_attempt`."""
    q = select(CohortQuizQuestion).where(CohortQuizQuestion.is_active.is_(True))
    if topics:
        q = q.where(CohortQuizQuestion.topic.in_(topics))
    pool = (await db.execute(q)).scalars().all()
    if not pool:
        # Checked before touching the existing rows — a topic filter that
        # matches nothing (a typo, an all-retired topic) must not wipe a
        # template's current question set for zero replacement.
        raise HTTPException(status.HTTP_409_CONFLICT, detail="No active questions match the selected topics")

    by_topic: dict[str, list[CohortQuizQuestion]] = {}
    for question in pool:
        by_topic.setdefault(question.topic, []).append(question)
    topic_names = list(by_topic.keys())
    random.shuffle(topic_names)
    for questions in by_topic.values():
        random.shuffle(questions)

    drawn: list[CohortQuizQuestion] = []
    while len(drawn) < count:
        progressed = False
        for topic in topic_names:
            if len(drawn) >= count:
                break
            bucket = by_topic[topic]
            if bucket:
                drawn.append(bucket.pop())
                progressed = True
        if not progressed:
            break  # every topic's pool is exhausted — fewer than `count` exist, draw what there is
    random.shuffle(drawn)

    # Delete-then-insert, wrapped in a SAVEPOINT — two concurrent
    # generate/regenerate calls on the same template would otherwise both
    # delete the same rows and then collide inserting fresh ones at the
    # same positions. Same guard idiom `add_template_question` uses for
    # its own race, including the narrow re-raise: only swallow the
    # specific expected constraint, not any IntegrityError (a hard-deleted
    # question between the SELECT above and this flush, say, should
    # surface as itself, not a misleading "try again").
    try:
        async with db.begin_nested():
            await db.execute(
                sa_delete(CohortQuizTemplateQuestion).where(CohortQuizTemplateQuestion.template_id == template_id)
            )
            rows = [
                CohortQuizTemplateQuestion(id=uuid.uuid4(), template_id=template_id, question_id=question.id, position=i)
                for i, question in enumerate(drawn, start=1)
            ]
            db.add_all(rows)
            await db.flush()
    except IntegrityError as e:
        if "uq_cohort_quiz_template_question_position" not in str(e.orig) and "uq_cohort_quiz_template_question_unique" not in str(e.orig):
            raise
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Another update to this template's questions happened at the same time — try again",
        )
    return rows


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
    """Preserves the template's configured question order.
    Option order is preserved as authored."""
    order = []
    for q in questions:
        idxs = list(range(len(q.options))) if q.options else []
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
        .order_by(CohortQuizTemplateQuestion.position.asc())
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
        if q is None:
            continue
        option_order: list[int] = entry.get("option_order", [])
        q_options = q.options or []
        if len(q_options) > 0 and max(option_order, default=-1) >= len(q_options):
            continue
        resolved.append((entry, q))
    return resolved


async def get_attempt_questions(db: AsyncSession, attempt: CohortQuizAttempt) -> list[dict]:
    """The attempt's questions for display — presentation order, options in
    the persisted shuffled order, `is_correct` never included."""
    resolved = await _resolve_question_order(db, attempt)
    out = []
    for entry, q in resolved:
        option_order: list[int] = entry.get("option_order", [])
        q_options = q.options or []
        out.append({
            "question_id": q.id, "topic": q.topic, "difficulty": q.difficulty,
            "time_limit_seconds": q.time_limit_seconds, "prompt": q.prompt,
            "options": [q_options[i]["text"] for i in option_order] if q_options else [],
            "question_type": q.question_type or "mcq",
            "is_optional": getattr(q, "is_optional", False),
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
    scorable_total = 0
    topic_breakdown: dict[str, dict[str, int]] = {}

    new_answers = []
    for entry, q in resolved:
        qid = q.id
        q_type = q.question_type or "mcq"
        option_order: list[int] = entry.get("option_order", [])
        answer = answers_by_qid.get(str(qid))
        q_options = q.options or []

        is_textarea = (q_type == "textarea")
        is_multiselect = (q_type in ("multiselect", "multiple_choice"))
        has_correct_option = any(o.get("is_correct") for o in q_options)

        text_ans = None
        selected_original_index = None
        selected_original_indices = None
        is_correct = None

        if is_textarea:
            text_ans = answer.text_answer.strip() if (answer and answer.text_answer) else None
            is_correct = None
        elif is_multiselect:
            sel_pos = []
            if answer:
                if answer.selected_option_indices is not None:
                    sel_pos = answer.selected_option_indices
                elif answer.selected_option_index is not None:
                    sel_pos = [answer.selected_option_index]
            selected_original_indices = [
                option_order[p] for p in sel_pos
                if 0 <= p < len(option_order)
            ]
            selected_original_index = selected_original_indices[0] if selected_original_indices else None

            if not has_correct_option:
                is_correct = None
            else:
                scorable_total += 1
                correct_orig = {i for i, o in enumerate(q_options) if o.get("is_correct")}
                is_correct = bool(set(selected_original_indices) == correct_orig)
                if is_correct:
                    score += 1
                bucket = topic_breakdown.setdefault(q.topic, {"correct": 0, "total": 0})
                bucket["total"] += 1
                if is_correct:
                    bucket["correct"] += 1
        elif not has_correct_option:
            selected_position = answer.selected_option_index if answer else None
            selected_original_index = (
                option_order[selected_position]
                if selected_position is not None and 0 <= selected_position < len(option_order)
                else None
            )
            selected_original_indices = [selected_original_index] if selected_original_index is not None else []
            is_correct = None
        else:
            scorable_total += 1
            selected_position = answer.selected_option_index if answer else None
            selected_original_index = (
                option_order[selected_position]
                if selected_position is not None and 0 <= selected_position < len(option_order)
                else None
            )
            selected_original_indices = [selected_original_index] if selected_original_index is not None else []
            is_correct = selected_original_index is not None and bool(q_options[selected_original_index].get("is_correct"))

            if is_correct:
                score += 1
            bucket = topic_breakdown.setdefault(q.topic, {"correct": 0, "total": 0})
            bucket["total"] += 1
            if is_correct:
                bucket["correct"] += 1

        new_answers.append(CohortQuizAnswer(
            id=uuid.uuid4(), attempt_id=attempt.id, question_id=qid, topic=q.topic,
            selected_option_index=selected_original_index,
            selected_option_indices=selected_original_indices,
            text_answer=text_ans,
            is_correct=is_correct,
            timed_out=bool(answer.timed_out) if answer else True,
            time_taken_seconds=answer.time_taken_seconds if answer else None,
        ))

    try:
        async with db.begin_nested():
            db.add_all(new_answers)
            attempt.status = "submitted"
            attempt.score = score if scorable_total > 0 else None
            attempt.total = scorable_total
            attempt.topic_breakdown = topic_breakdown
            attempt.submitted_at = datetime.now(timezone.utc)
            await db.flush()
    except IntegrityError as e:
        if "uq_cohort_quiz_answer_attempt_question" not in str(e.orig):
            raise
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This quiz is already submitted")
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
            continue
        option_order: list[int] = entry.get("option_order", [])
        q_options = q.options or []
        correct_original_indices = [i for i, o in enumerate(q_options) if o.get("is_correct")]
        correct_indices = [
            option_order.index(i)
            for i in correct_original_indices
            if i in option_order
        ]
        correct_idx = correct_indices[0] if correct_indices else None

        sel_orig_indices = (
            answer.selected_option_indices
            if answer.selected_option_indices is not None
            else ([answer.selected_option_index] if answer.selected_option_index is not None else [])
        )
        selected_indices = [
            option_order.index(i)
            for i in sel_orig_indices
            if i in option_order
        ]
        selected_idx = (
            option_order.index(answer.selected_option_index)
            if (answer.selected_option_index is not None and answer.selected_option_index in option_order)
            else (selected_indices[0] if selected_indices else None)
        )
        out.append({
            "question_id": q.id, "topic": q.topic, "prompt": q.prompt,
            "options": [q_options[i]["text"] for i in option_order] if q_options else [],
            "selected_index": selected_idx,
            "selected_indices": selected_indices,
            "correct_index": correct_idx,
            "correct_indices": correct_indices,
            "is_correct": answer.is_correct,
            "explanation": q.explanation,
            "time_taken_seconds": answer.time_taken_seconds,
            "timed_out": answer.timed_out,
            "question_type": q.question_type or "mcq",
            "text_answer": answer.text_answer,
            "is_optional": getattr(q, "is_optional", False),
        })
    return out


def result_out(attempt: CohortQuizAttempt, review: list[dict]) -> CohortQuizResultOut:
    """Shared by the student's own `/quiz/result` and `/quiz/submit`
    routes and the ops/instructor review endpoint — same attempt, same
    shape, just reached by a different lookup (current user vs. an
    assignment's student)."""
    return CohortQuizResultOut(
        id=attempt.id, status=attempt.status, score=attempt.score, total=attempt.total,
        topic_breakdown=attempt.topic_breakdown, submitted_at=attempt.submitted_at,
        questions=[CohortQuizQuestionReviewOut(**r) for r in review],
    )


async def reset_attempt(db: AsyncSession, *, program_item_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Ops/instructor "let them retake" action — deletes the student's
    attempt (cascading to its answers) so their next visit to this quiz
    starts a brand-new one: fresh `CohortQuizAttempt` row, fresh
    `question_order`, fresh per-question timers. The checklist item
    reverts to not-done on the next `refresh_item_progress` call, same as
    any other auto-tracked item that un-completes. Works on an
    in-progress attempt too (unsticking one), not just a submitted one.
    Returns False if the student never started this quiz at all."""
    attempt = await get_own_attempt(db, program_item_id=program_item_id, user_id=user_id)
    if attempt is None:
        return False
    await db.delete(attempt)
    await db.flush()
    return True


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


async def get_cohort_quiz_analysis(
    db: AsyncSession, cohort_id: uuid.UUID, *, include_observers: bool = False,
    mode: str = "student",
) -> dict:
    """Live topic and score breakdown for an entire cohort, both overall and grouped per quiz item.

    Observer mode (2026-10): partitioned by mode ('student', 'observer', 'all').
    Defaults to 'student' so staff test runs do not alter student metrics."""
    effective_mode = "all" if include_observers else (mode or "student")

    from app.models.lms.program import LmsProgramAssignment
    observer_ids = list((await db.execute(
        select(LmsProgramAssignment.user_id).where(
            LmsProgramAssignment.cohort_id == cohort_id,
            LmsProgramAssignment.mode == "observer",
        )
    )).scalars().all())

    stmt = (
        select(CohortQuizAttempt, LmsProgramItem.title)
        .outerjoin(LmsProgramItem, CohortQuizAttempt.program_item_id == LmsProgramItem.id)
        .where(
            CohortQuizAttempt.cohort_id == cohort_id,
            CohortQuizAttempt.status == "submitted",
        )
    )
    if effective_mode == "observer":
        if not observer_ids:
            return {
                "cohort_id": str(cohort_id),
                "total_attempts": 0,
                "overall_average_score_pct": 0.0,
                "overall_topic_breakdown": {},
                "quizzes": [],
                "questions": [],
            }
        stmt = stmt.where(CohortQuizAttempt.user_id.in_(observer_ids))
    elif effective_mode == "student":
        if observer_ids:
            stmt = stmt.where(CohortQuizAttempt.user_id.not_in(observer_ids))
    results = (await db.execute(stmt)).all()

    overall_breakdown: dict[str, dict[str, int]] = {}
    quizzes_map: dict[str, dict] = {}
    total_score = 0
    total_possible = 0

    for attempt, quiz_title in results:
        quiz_id_str = str(attempt.program_item_id)
        title = quiz_title or "Cohort Knowledge Quiz"

        if quiz_id_str not in quizzes_map:
            quizzes_map[quiz_id_str] = {
                "quiz_id": quiz_id_str,
                "quiz_title": title,
                "total_attempts": 0,
                "total_score": 0,
                "total_possible": 0,
                "topic_breakdown": {},
            }

        q_entry = quizzes_map[quiz_id_str]
        q_entry["total_attempts"] += 1
        if attempt.score is not None:
            q_entry["total_score"] += attempt.score
            total_score += attempt.score
        q_entry["total_possible"] += (attempt.total or 0)
        total_possible += (attempt.total or 0)

        # Aggregate topics
        for topic, counts in (attempt.topic_breakdown or {}).items():
            # Overall
            o_bucket = overall_breakdown.setdefault(topic, {"correct": 0, "total": 0})
            o_bucket["correct"] += counts.get("correct", 0)
            o_bucket["total"] += counts.get("total", 0)

            # Per-quiz
            q_bucket = q_entry["topic_breakdown"].setdefault(topic, {"correct": 0, "total": 0})
            q_bucket["correct"] += counts.get("correct", 0)
            q_bucket["total"] += counts.get("total", 0)

    quizzes_list = list(quizzes_map.values())
    overall_avg_pct = round((total_score / total_possible) * 100) if total_possible > 0 else 0
    for q in quizzes_list:
        q["average_score_pct"] = round((q["total_score"] / q["total_possible"]) * 100) if q["total_possible"] > 0 else 0

    # Questions breakdown across submitted attempts
    answers_stmt = (
        select(
            CohortQuizAnswer.question_id,
            CohortQuizAnswer.topic,
            CohortQuizAnswer.is_correct,
            CohortQuizQuestion.prompt,
            CohortQuizQuestion.difficulty,
            CohortQuizAttempt.program_item_id,
            LmsProgramItem.title.label("quiz_title"),
        )
        .join(CohortQuizAttempt, CohortQuizAnswer.attempt_id == CohortQuizAttempt.id)
        .outerjoin(CohortQuizQuestion, CohortQuizAnswer.question_id == CohortQuizQuestion.id)
        .outerjoin(LmsProgramItem, CohortQuizAttempt.program_item_id == LmsProgramItem.id)
        .where(
            CohortQuizAttempt.cohort_id == cohort_id,
            CohortQuizAttempt.status == "submitted",
        )
    )
    if effective_mode == "observer":
        if not observer_ids:
            return {
                "cohort_id": str(cohort_id),
                "total_attempts": 0,
                "overall_average_score_pct": 0.0,
                "overall_topic_breakdown": {},
                "quizzes": [],
                "questions": [],
            }
        answers_stmt = answers_stmt.where(CohortQuizAttempt.user_id.in_(observer_ids))
    elif effective_mode == "student":
        if observer_ids:
            answers_stmt = answers_stmt.where(CohortQuizAttempt.user_id.not_in(observer_ids))
    ans_rows = (await db.execute(answers_stmt)).all()

    questions_map: dict[tuple[str, str], dict] = {}
    for qid, topic, is_correct, prompt, difficulty, p_item_id, q_title in ans_rows:
        qid_str = str(qid) if qid else "unknown"
        p_item_id_str = str(p_item_id) if p_item_id else "unknown"
        key = (qid_str, p_item_id_str)

        if key not in questions_map:
            questions_map[key] = {
                "question_id": qid_str,
                "quiz_id": p_item_id_str,
                "quiz_title": q_title or "Cohort Knowledge Quiz",
                "topic": topic or "General",
                "prompt": prompt or f"Question ({qid_str[:8]})",
                "difficulty": difficulty,
                "correct_count": 0,
                "incorrect_count": 0,
                "total_answers": 0,
                "accuracy_pct": 0,
            }

        q_stat = questions_map[key]
        q_stat["total_answers"] += 1
        if is_correct is True:
            q_stat["correct_count"] += 1
        elif is_correct is False:
            q_stat["incorrect_count"] += 1

    for q_stat in questions_map.values():
        scorable = q_stat["correct_count"] + q_stat["incorrect_count"]
        if scorable > 0:
            q_stat["accuracy_pct"] = round((q_stat["correct_count"] / scorable) * 100)
        else:
            q_stat["accuracy_pct"] = None

    # Sort questions by most wrong by default
    questions_list = sorted(
        questions_map.values(),
        key=lambda x: (x["incorrect_count"], -(x["accuracy_pct"] if x["accuracy_pct"] is not None else -1)),
        reverse=True,
    )

    return {
        "cohort_id": str(cohort_id),
        "total_attempts": len(results),
        "overall_average_score_pct": overall_avg_pct,
        "overall_topic_breakdown": overall_breakdown,
        "quizzes": quizzes_list,
        "questions": questions_list,
    }

