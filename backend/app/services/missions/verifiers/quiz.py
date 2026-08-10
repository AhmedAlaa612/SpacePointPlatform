"""The `quiz` mission kind (P5-3) — auto-graded, reusing the exact LMS
grader (`services/lms/quiz.py::grade_quiz`) rather than forking the scoring
math. A variant's `config` is `{pass_threshold, questions}` — literally the
same shape `AdminContentQuiz` already validates for LMS quiz items, so
authoring reuses that model too (P5-4).

Safe to build now that P2-3 closed the review-sheet oracle: `grade_quiz`'s
returned `questions` review reveals every `correct_text`, same as the LMS
quiz's post-submit sheet. `submit_quiz_attempt` only grades from
`in_progress` and decides immediately — a retry is a new attempt via
`start_attempt`, never a resubmission of the same one — so there is no
submit(garbage) -> read the leak -> resubmit path here either.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.mission import MissionAttempt, MissionVariant
from app.services.lms.quiz import grade_quiz
from app.services.missions.attempts import decide_attempt


async def submit_quiz_attempt(
    db: AsyncSession, *, attempt: MissionAttempt, variant: MissionVariant, answers: list[int],
) -> tuple[MissionAttempt, dict]:
    """Grades immediately — no human review, unlike the `submission` kind.
    Returns `(attempt, review_sheet)`, the review sheet shaped exactly like
    `grade_quiz`'s `{score, passed, questions}`.
    """
    if attempt.status != "in_progress":
        raise HTTPException(409, detail=f"Attempt is '{attempt.status}', not 'in_progress' — cannot submit")

    config = variant.config or {}
    questions: list[dict] = config.get("questions") or []
    pass_threshold = config.get("pass_threshold", 0)

    graded = grade_quiz(questions=questions, answers=answers, pass_threshold=pass_threshold)

    attempt.payload = {**(attempt.payload or {}), "answers": answers}
    attempt.submitted_at = datetime.now(timezone.utc)
    await db.flush()

    decided = await decide_attempt(db, attempt=attempt, passed=graded["passed"], score=graded["score"])
    return decided, graded
