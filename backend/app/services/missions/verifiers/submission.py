"""The `submission` mission kind (P5-2) — a student submits an artifact
(a link, same shape as `models/interns/submission.py::TaskSubmission`), a
staff reviewer scores it. Mirrors that flow's status/score/review_comment
state, kept in `mission_attempts.payload` rather than a second table — one
attempt table for every kind is the point of the design (MISSIONS_REPORT.md
Ch.2, idea 1).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.mission import MissionAttempt
from app.services.missions.attempts import decide_attempt


async def submit_submission_attempt(
    db: AsyncSession, *, attempt: MissionAttempt, artifact_url: str, notes: str | None = None
) -> MissionAttempt:
    """Student hands in their work. Only legal from `in_progress` — a
    decided attempt is retried via a new `start_attempt` call, not a
    resubmission of the same one.
    """
    if attempt.status != "in_progress":
        raise HTTPException(409, detail=f"Attempt is '{attempt.status}', not 'in_progress' — cannot submit")
    attempt.payload = {**(attempt.payload or {}), "artifact_url": artifact_url, "notes": notes}
    attempt.status = "submitted"
    attempt.submitted_at = datetime.now(timezone.utc)
    await db.flush()
    return attempt


async def review_submission_attempt(
    db: AsyncSession,
    *,
    attempt: MissionAttempt,
    reviewer_id: uuid.UUID,
    passed: bool,
    score: Decimal | float | None = None,
    review_comment: str | None = None,
) -> MissionAttempt:
    """A staff reviewer decides an attempt already awaiting review."""
    if attempt.status != "submitted":
        raise HTTPException(409, detail=f"Attempt is '{attempt.status}', not 'submitted' — nothing to review")
    attempt.payload = {**(attempt.payload or {}), "review_comment": review_comment}
    await db.flush()
    return await decide_attempt(db, attempt=attempt, passed=passed, score=score, decided_by=reviewer_id)
