"""Mission attempt lifecycle (P5-2, Phase 2 Stage 5, 2026-08-11).

Two functions every verifier kind shares: `start_attempt` (template →
instance, single-flight — a student can't be "in progress" on two attempts
of the same mission at once) and `decide_attempt` (the one place a verifier
lands a final passed/failed and, on pass, mints the points award). Kind-
specific grading lives in `services/missions/verifiers/*`; this module has
no opinion on what "passed" means for any given kind.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.mission import MissionAttempt, MissionVariant
from app.services.lms.points import award_points

MISSION_POINTS_SOURCE = "mission"


async def start_attempt(
    db: AsyncSession, *, user_id: uuid.UUID, mission_id: uuid.UUID, variant_id: uuid.UUID
) -> MissionAttempt:
    """Resumes this user's in-progress attempt on `mission_id` if one exists
    (ignoring the requested `variant_id` in that case — finish what you
    started before beginning something new), otherwise starts a new one at
    `attempt_no = max(existing) + 1`.
    """
    existing = await db.scalar(
        select(MissionAttempt)
        .where(
            MissionAttempt.mission_id == mission_id,
            MissionAttempt.user_id == user_id,
            MissionAttempt.status == "in_progress",
        )
        .order_by(MissionAttempt.started_at.desc())
    )
    if existing is not None:
        return existing

    max_no = await db.scalar(
        select(func.max(MissionAttempt.attempt_no)).where(
            MissionAttempt.mission_id == mission_id,
            MissionAttempt.user_id == user_id,
        )
    )
    attempt = MissionAttempt(
        id=uuid.uuid4(),
        mission_id=mission_id,
        variant_id=variant_id,
        user_id=user_id,
        attempt_no=(max_no or 0) + 1,
        status="in_progress",
    )
    db.add(attempt)
    await db.flush()
    return attempt


async def decide_attempt(
    db: AsyncSession,
    *,
    attempt: MissionAttempt,
    passed: bool,
    score: Decimal | float | None = None,
    decided_by: uuid.UUID | None = None,
) -> MissionAttempt:
    """Flips `attempt` to passed/failed and, on pass, awards the variant's
    points. Idempotency key is `(mission_id, variant_id)` — passing the same
    variant again on a later attempt doesn't re-award, but passing a
    *harder* variant of the same mission is a new key and does (replaying at
    higher difficulty stays meaningful, MISSIONS_REPORT.md Ch.2).
    """
    attempt.status = "passed" if passed else "failed"
    attempt.score = score
    attempt.decided_at = datetime.now(timezone.utc)
    attempt.decided_by = decided_by
    await db.flush()

    if passed:
        variant = await db.get(MissionVariant, attempt.variant_id)
        await award_points(
            db,
            user_id=attempt.user_id,
            source=MISSION_POINTS_SOURCE,
            points=variant.points,
            idempotency_key=f"{attempt.mission_id}:{attempt.variant_id}",
            ref={
                "attempt_id": str(attempt.id),
                "mission_id": str(attempt.mission_id),
                "variant_id": str(attempt.variant_id),
            },
        )
    return attempt
