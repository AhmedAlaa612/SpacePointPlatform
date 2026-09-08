"""Question selection, shuffling, and grading for one instructor's
assessment attempt (2026-09). See `app/models/instructor_assessment/
__init__.py` for the domain overview.

Draw algorithm (locked in with the operator):
1. Shuffle categories; round-robin one *critical*-flagged question at a
   time (random pick within category) until a floor of `CRITICAL_FLOOR` is
   reached — critical questions cluster in only a few categories, so a
   flat random draw could plausibly land zero of them.
2. Shuffle categories again; round-robin one not-yet-used question per
   category (any critical status) for the remaining slots, skipping
   exhausted categories, until `DRAW_SIZE` total.
3. Shuffle the final set into presentation order; each question's own
   options get an independently shuffled order, persisted alongside the
   draw so a page refresh mid-attempt never reshuffles anything.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.instructor_assessment.attempt import AssessmentAnswer, AssessmentAttempt
from app.models.instructor_assessment.config import AssessmentQuestion
from app.models.sessions.cohort_call import CohortCall
from app.models.user import User

CRITICAL_FLOOR = 3
DRAW_SIZE = 15


async def get_assignment_for_cohort_call(db: AsyncSession, cohort_call_id: UUID) -> Optional[AssessmentCohortAssignment]:
    """The config gating this opportunity, if any — the whole on/off switch.
    None means this cohort never opted in; every caller must treat that as
    "no assessment required", not an error."""
    call = await db.get(CohortCall, cohort_call_id)
    if call is None:
        return None
    return (await db.execute(
        select(AssessmentCohortAssignment).where(AssessmentCohortAssignment.cohort_id == call.cohort_id)
    )).scalars().first()


def _round_robin_draw(
    by_category: dict[str, list[AssessmentQuestion]], count: int, exclude_ids: set[UUID],
) -> list[AssessmentQuestion]:
    """Shuffle category order, take one not-yet-used-or-excluded question at
    a time from each in turn, skipping exhausted categories, looping back
    to the start of the list, until `count` are collected or the whole
    (category-scoped) pool runs out."""
    categories = list(by_category.keys())
    random.shuffle(categories)
    pools = {cat: [q for q in qs if q.id not in exclude_ids] for cat, qs in by_category.items()}
    for pool in pools.values():
        random.shuffle(pool)

    drawn: list[AssessmentQuestion] = []
    while len(drawn) < count:
        progressed = False
        for cat in categories:
            if len(drawn) >= count:
                break
            pool = pools[cat]
            if pool:
                q = pool.pop()
                drawn.append(q)
                exclude_ids.add(q.id)
                progressed = True
        if not progressed:
            break  # every category's pool is exhausted — fewer than `count` exist
    return drawn


async def draw_questions(db: AsyncSession, config_id: UUID) -> list[AssessmentQuestion]:
    questions = (await db.execute(
        select(AssessmentQuestion).where(
            AssessmentQuestion.config_id == config_id, AssessmentQuestion.is_active.is_(True),
        )
    )).scalars().all()

    by_category: dict[str, list[AssessmentQuestion]] = {}
    for q in questions:
        by_category.setdefault(q.category, []).append(q)

    critical_by_category = {cat: [q for q in qs if q.critical] for cat, qs in by_category.items()}
    critical_by_category = {cat: qs for cat, qs in critical_by_category.items() if qs}
    critical_available = sum(len(qs) for qs in critical_by_category.values())

    exclude_ids: set[UUID] = set()
    critical_drawn = _round_robin_draw(critical_by_category, min(CRITICAL_FLOOR, critical_available), exclude_ids)
    normal_drawn = _round_robin_draw(by_category, DRAW_SIZE - len(critical_drawn), exclude_ids)

    drawn = critical_drawn + normal_drawn
    random.shuffle(drawn)
    return drawn


def _build_question_order(questions: list[AssessmentQuestion]) -> list[dict]:
    """One entry per drawn question, in presentation order, each carrying
    its own independently-shuffled option order — `option_order[i]` is
    which original `options` index is shown at displayed position `i`."""
    order = []
    for q in questions:
        idxs = list(range(len(q.options)))
        random.shuffle(idxs)
        order.append({"question_id": str(q.id), "option_order": idxs})
    return order


async def start_attempt(db: AsyncSession, *, cohort_call_id: UUID, user: User) -> AssessmentAttempt:
    """Get-or-create — a page refresh mid-attempt must never reshuffle the
    questions or answer options out from under the instructor (same reason
    the LMS quiz's `quiz_question_order` exists)."""
    existing = (await db.execute(
        select(AssessmentAttempt).where(
            AssessmentAttempt.cohort_call_id == cohort_call_id, AssessmentAttempt.user_id == user.id,
        )
    )).scalars().first()
    if existing is not None:
        return existing

    assignment = await get_assignment_for_cohort_call(db, cohort_call_id)
    if assignment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No assessment is required for this opportunity")

    questions = await draw_questions(db, assignment.config_id)
    if len(questions) < DRAW_SIZE:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="The question bank doesn't have enough active questions to draw a full assessment",
        )

    attempt = AssessmentAttempt(
        id=uuid.uuid4(), config_id=assignment.config_id, cohort_call_id=cohort_call_id, user_id=user.id,
        question_order=_build_question_order(questions), status="in_progress", total=DRAW_SIZE,
    )
    db.add(attempt)
    await db.flush()
    return attempt


async def get_own_attempt(db: AsyncSession, cohort_call_id: UUID, user_id: UUID) -> Optional[AssessmentAttempt]:
    return (await db.execute(
        select(AssessmentAttempt).where(
            AssessmentAttempt.cohort_call_id == cohort_call_id, AssessmentAttempt.user_id == user_id,
        )
    )).scalars().first()


async def get_attempt_questions(db: AsyncSession, attempt: AssessmentAttempt) -> list[dict]:
    """The attempt's drawn questions for display — presentation order,
    options in the persisted shuffled order, `is_correct` never included."""
    question_ids = [uuid.UUID(o["question_id"]) for o in attempt.question_order]
    rows = (await db.execute(
        select(AssessmentQuestion).where(AssessmentQuestion.id.in_(question_ids))
    )).scalars().all()
    by_id = {q.id: q for q in rows}

    out = []
    for entry in attempt.question_order:
        q = by_id.get(uuid.UUID(entry["question_id"]))
        if q is None:
            continue  # question deactivated/removed since the draw — skip rather than error
        ordered_options = [q.options[i]["text"] for i in entry["option_order"]]
        out.append({
            "question_id": q.id, "category": q.category, "prompt": q.prompt,
            "options": ordered_options, "critical": q.critical,
        })
    return out


async def submit_attempt(db: AsyncSession, attempt: AssessmentAttempt, answers: dict[str, Optional[int]]) -> AssessmentAttempt:
    """`answers` maps question_id (str) -> the DISPLAYED option position the
    instructor picked (None if they left it blank/timed out). Grades against
    the persisted `question_order` only — never the raw pool, and never
    trusts a client-supplied "is_correct"."""
    if attempt.status == "submitted":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This attempt is already submitted")

    question_ids = [uuid.UUID(o["question_id"]) for o in attempt.question_order]
    rows = (await db.execute(
        select(AssessmentQuestion).where(AssessmentQuestion.id.in_(question_ids))
    )).scalars().all()
    by_id = {q.id: q for q in rows}

    score = 0
    critical_correct = 0
    critical_total = 0
    category_breakdown: dict[str, dict[str, int]] = {}

    for entry in attempt.question_order:
        qid = uuid.UUID(entry["question_id"])
        q = by_id.get(qid)
        if q is None:
            continue
        option_order: list[int] = entry["option_order"]
        selected_position = answers.get(str(qid))
        selected_original_index = (
            option_order[selected_position]
            if selected_position is not None and 0 <= selected_position < len(option_order)
            else None
        )
        is_correct = selected_original_index is not None and bool(q.options[selected_original_index].get("is_correct"))

        if is_correct:
            score += 1
        if q.critical:
            critical_total += 1
            if is_correct:
                critical_correct += 1
        bucket = category_breakdown.setdefault(q.category, {"correct": 0, "total": 0})
        bucket["total"] += 1
        if is_correct:
            bucket["correct"] += 1

        db.add(AssessmentAnswer(
            id=uuid.uuid4(), attempt_id=attempt.id, question_id=qid,
            selected_option_index=selected_original_index, is_correct=is_correct,
        ))

    attempt.status = "submitted"
    attempt.score = score
    attempt.critical_correct = critical_correct
    attempt.critical_total = critical_total
    attempt.category_breakdown = category_breakdown
    attempt.submitted_at = datetime.now(timezone.utc)
    await db.flush()
    return attempt
