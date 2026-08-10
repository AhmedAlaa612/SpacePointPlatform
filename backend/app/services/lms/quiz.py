"""LMS quiz grading (LM1-2) — server-side, never the client.

The student's answers are indices into each question's options; correctness
is decided here against `content["questions"]`, and `pass_threshold == 0`
means any submission passes (D7). Retries are unlimited: each submission
increments `quiz_attempts` and raises `best_score` to the best so far, but a
pass is terminal — the item flips to `completed` once, `completed_at` is set
once, and a later failed retry never downgrades it back. The review payload
is the *post-submit* answer sheet, which is exactly when `explanation` is
allowed to leave the server (§2 — the leak test governs `student_view`,
the pre-submit path).

P2-3 (Phase 2 Stage 2, audit §9.2): `first_score`/`first_scored_at` are
written once, on the first-ever submission, and drive the points award —
never `best_score`, because the review sheet above is itself an answer
oracle on unlimited retries (see services/lms/points.py::award_quiz_points
for the full reasoning). `hints_used` (incremented by `check_quiz_answer`)
never affects grading or completion, only how many points that first
submission is worth.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.course import ModuleItem
from app.models.lms.enrollment import ItemProgress
from app.services.lms.points import award_quiz_points


async def _progress_row(db: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID) -> ItemProgress:
    row = (await db.execute(
        select(ItemProgress).where(
            ItemProgress.user_id == user_id,
            ItemProgress.item_id == item_id,
        )
    )).scalars().first()
    if row is None:
        row = ItemProgress(
            id=uuid.uuid4(),
            user_id=user_id,
            item_id=item_id,
            status="not_started",
            quiz_attempts=0,
            hints_used=0,
        )
        db.add(row)
    return row


async def check_quiz_answer(
    db: AsyncSession, *, user_id: uuid.UUID, item_id: uuid.UUID, question_index: int, answer: int,
) -> dict:
    """Live per-question feedback (2026-08-09), same posture as
    `checkpoint.py`'s `submit_checkpoint_answer`: no completion/grading
    state touched — the real, once-per-attempt grade still happens in
    `submit_quiz` below. The one thing this DOES record (P2-3, 2026-08-10)
    is `item_progress.hints_used`, so the points award (keyed on the first
    submission) can scale down for a first attempt that leaned on live
    feedback — completion and unlock still ignore it entirely."""
    item = await db.get(ModuleItem, item_id)
    if item is None or item.kind != "quiz":
        raise HTTPException(404, detail="Quiz item not found")

    questions: list[dict] = (item.content or {}).get("questions") or []
    if not (0 <= question_index < len(questions)):
        raise HTTPException(400, detail="question_index is out of range")

    options = questions[question_index].get("options") or []
    if not isinstance(answer, int) or isinstance(answer, bool) or not (0 <= answer < len(options)):
        raise HTTPException(400, detail="answer is out of range")

    row = await _progress_row(db, user_id, item_id)
    row.hints_used += 1
    await db.flush()

    return {
        "correct": bool(options[answer].get("is_correct")),
        "explanation": questions[question_index].get("explanation"),
        "correct_text": next((o.get("text") for o in options if o.get("is_correct")), None),
    }


async def submit_quiz(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    answers: list[int],
) -> dict:
    """Grade a quiz submission against the authored content and record it.

    `answers` is one option index per question, in order. A mismatch in
    count or an out-of-range index is a 400 — the client is not trusted to
    state its own score. Returns the review sheet: score, pass state, the
    attempts/best counters, and per-question correctness + explanation.
    """
    item = await db.get(ModuleItem, item_id)
    if item is None:
        raise HTTPException(404, detail="Item not found")
    if item.kind != "quiz":
        raise HTTPException(400, detail="Only quiz items can be submitted")

    content = item.content or {}
    questions: list[dict] = content.get("questions") or []
    pass_threshold = content.get("pass_threshold", 0)

    if len(answers) != len(questions):
        raise HTTPException(
            400, detail="Answer count does not match the number of questions"
        )
    for idx, answer in enumerate(answers):
        options = questions[idx].get("options") or []
        if not isinstance(answer, int) or not (0 <= answer < len(options)):
            raise HTTPException(
                400, detail=f"Answer for question {idx + 1} is out of range"
            )

    if questions:
        correct = sum(
            1
            for idx, answer in enumerate(answers)
            if (questions[idx].get("options") or [])[answer].get("is_correct")
        )
        score = round(correct / len(questions) * 100, 2)
    else:
        correct = 0
        score = 0.0

    if not (0 <= pass_threshold <= 100):
        raise HTTPException(400, detail="pass_threshold must be between 0 and 100")
    passed = pass_threshold == 0 or score >= pass_threshold

    row = await _progress_row(db, user_id, item_id)
    row.quiz_attempts += 1
    row.updated_at = datetime.now(timezone.utc)

    new_best = Decimal(str(score))
    row.best_score = new_best if row.best_score is None else max(row.best_score, new_best)

    # P2-3: written once, on the first-ever submission, and never again —
    # `first_score is None` is the guard, both for "is this the first
    # attempt" and for "has the points award already fired" (award_quiz_
    # points is itself idempotent too, but this avoids even trying twice).
    is_first_submission = row.first_score is None
    if is_first_submission:
        row.first_score = new_best
        row.first_scored_at = datetime.now(timezone.utc)

    if passed:
        if row.status != "completed":
            row.status = "completed"
            row.completed_at = datetime.now(timezone.utc)
    elif row.status != "completed":
        # a failed retry never un-completes a quiz that was already passed
        row.status = "in_progress"
    await db.flush()

    if is_first_submission:
        await award_quiz_points(
            db, user_id=user_id, item_id=item_id, first_score=row.first_score,
            hints_used_at_first_submit=row.hints_used, pass_threshold=pass_threshold,
        )

    review = [
        {
            "prompt": questions[idx].get("prompt"),
            "selected": answers[idx],
            "correct": bool((questions[idx].get("options") or [])[answers[idx]].get("is_correct")),
            "explanation": questions[idx].get("explanation"),
            # Safe to reveal post-submit — same moment `explanation` already
            # leaves the server (§2). Lets the review show "Your answer" vs
            # "Correct" instead of just an explanation blurb.
            "correct_text": next(
                (o.get("text") for o in (questions[idx].get("options") or []) if o.get("is_correct")), None,
            ),
        }
        for idx in range(len(questions))
    ]

    return {
        "score": score,
        "passed": passed,
        "pass_threshold": pass_threshold,
        "attempts": row.quiz_attempts,
        "best_score": float(row.best_score) if row.best_score is not None else None,
        "questions": review,
    }