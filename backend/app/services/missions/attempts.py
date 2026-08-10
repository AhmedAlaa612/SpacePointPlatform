"""Mission attempt lifecycle (P5-2, Phase 2 Stage 5/6, 2026-08-11).

Two functions every verifier kind shares: `start_attempt` (template →
instance, single-flight — an owner can't be "in progress" on two attempts
of the same mission at once) and `decide_attempt` (the one place a verifier
lands a final passed/failed and, on pass, mints the points award). Kind-
specific grading lives in `services/missions/verifiers/*`; this module has
no opinion on what "passed" means for any given kind.

P6-2: `start_attempt` takes `user_id` XOR `team_id` — exactly one, matching
`mission_attempts`' own CHECK constraint. A team attempt snapshots the
team's *current* roster into `MissionAttemptMember` at this exact moment;
`MissionTeamMember` can change afterward without touching that snapshot.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.mission import MissionAttempt, MissionAttemptMember, MissionVariant
from app.services.lms.points import award_points
from app.services.missions.embedding import complete_embedded_items
from app.services.missions.teams import team_member_ids

MISSION_POINTS_SOURCE = "mission"


async def start_attempt(
    db: AsyncSession, *, mission_id: uuid.UUID, variant_id: uuid.UUID,
    user_id: uuid.UUID | None = None, team_id: uuid.UUID | None = None,
) -> MissionAttempt:
    """Resumes the owner's (a user or a team — exactly one) in-progress
    attempt on `mission_id` if one exists (ignoring the requested
    `variant_id` in that case — finish what you started before beginning
    something new), otherwise starts a new one at
    `attempt_no = max(existing) + 1`, scoped to the same owner.
    """
    if (user_id is None) == (team_id is None):
        raise HTTPException(400, detail="Exactly one of user_id or team_id is required")
    owner_column = MissionAttempt.user_id if user_id is not None else MissionAttempt.mission_team_id
    owner_value = user_id if user_id is not None else team_id

    existing = await db.scalar(
        select(MissionAttempt)
        .where(
            MissionAttempt.mission_id == mission_id,
            owner_column == owner_value,
            MissionAttempt.status == "in_progress",
        )
        .order_by(MissionAttempt.started_at.desc())
    )
    if existing is not None:
        return existing

    max_no = await db.scalar(
        select(func.max(MissionAttempt.attempt_no)).where(
            MissionAttempt.mission_id == mission_id,
            owner_column == owner_value,
        )
    )
    attempt = MissionAttempt(
        id=uuid.uuid4(),
        mission_id=mission_id,
        variant_id=variant_id,
        user_id=user_id,
        mission_team_id=team_id,
        attempt_no=(max_no or 0) + 1,
        status="in_progress",
    )
    db.add(attempt)
    await db.flush()

    if team_id is not None:
        for member_id in await team_member_ids(db, team_id=team_id):
            db.add(MissionAttemptMember(attempt_id=attempt.id, user_id=member_id))
        await db.flush()

    return attempt


async def _attempt_recipients(db: AsyncSession, attempt: MissionAttempt) -> list[uuid.UUID]:
    """Who a passing attempt owes points/completion to: the solo student,
    or (P6-3) every member of the `mission_attempt_members` snapshot frozen
    at `start_attempt` time — never live `MissionTeamMember` roster, which
    may have changed since."""
    if attempt.user_id is not None:
        return [attempt.user_id]
    rows = (await db.execute(
        select(MissionAttemptMember.user_id).where(MissionAttemptMember.attempt_id == attempt.id)
    )).scalars().all()
    return list(rows)


async def decide_attempt(
    db: AsyncSession,
    *,
    attempt: MissionAttempt,
    passed: bool,
    score: Decimal | float | None = None,
    decided_by: uuid.UUID | None = None,
) -> MissionAttempt:
    """Flips `attempt` to passed/failed and, on pass, awards the variant's
    points. Idempotency key is `(mission_id, variant_id)`, scoped per
    recipient — passing the same variant again on a later attempt doesn't
    re-award, but passing a *harder* variant of the same mission is a new
    key and does (replaying at higher difficulty stays meaningful,
    MISSIONS_REPORT.md Ch.2).

    A team attempt (P6-3) awards *every* member of the frozen roster
    individually — "collaborative work, individual leaderboard"
    (MISSIONS_REPORT.md Ch.2 idea 5) — each carrying `ref.team_id`, not a
    single shared award.
    """
    attempt.status = "passed" if passed else "failed"
    attempt.score = score
    attempt.decided_at = datetime.now(timezone.utc)
    attempt.decided_by = decided_by
    await db.flush()

    if passed:
        variant = await db.get(MissionVariant, attempt.variant_id)
        recipients = await _attempt_recipients(db, attempt)
        ref = {
            "attempt_id": str(attempt.id),
            "mission_id": str(attempt.mission_id),
            "variant_id": str(attempt.variant_id),
        }
        if attempt.mission_team_id is not None:
            ref["team_id"] = str(attempt.mission_team_id)
        for user_id in recipients:
            await award_points(
                db,
                user_id=user_id,
                source=MISSION_POINTS_SOURCE,
                points=variant.points,
                idempotency_key=f"{attempt.mission_id}:{attempt.variant_id}",
                ref=ref,
            )
        # Rule ① (Stage 5): never client-assertable — this is the only path
        # that can complete an embedded mission item's ItemProgress row.
        await complete_embedded_items(
            db, mission_id=attempt.mission_id, variant_id=attempt.variant_id, user_ids=recipients,
        )
    return attempt
