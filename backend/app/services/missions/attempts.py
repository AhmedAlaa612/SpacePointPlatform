"""Mission attempt lifecycle (P5-2, Phase 2 Stage 5/6, 2026-08-11).

Two functions every verifier kind shares: `start_attempt` (template →
instance — single-flight by default, resuming the owner's in-progress
attempt rather than starting a second one, unless the caller explicitly
asks for `force_new`; see its own docstring) and `decide_attempt` (the one
place a verifier lands a final passed/failed and, on pass, mints the
points award). Kind-specific grading lives in `services/missions/verifiers/*`;
this module has no opinion on what "passed" means for any given kind.

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
from app.services.teams import team_member_ids

MISSION_POINTS_SOURCE = "mission"


async def start_attempt(
    db: AsyncSession, *, mission_id: uuid.UUID, variant_id: uuid.UUID,
    user_id: uuid.UUID | None = None, team_id: uuid.UUID | None = None,
    force_new: bool = False, cohort_id: uuid.UUID | None = None,
) -> MissionAttempt:
    """Resumes the owner's (a user or a team — exactly one) in-progress
    attempt on `mission_id` if one exists *in the same cohort scope as this
    call* (ignoring the requested `variant_id` in that case — finish what
    you started before beginning something new), otherwise starts a new one
    at `attempt_no = max(existing) + 1`, scoped to the same owner. An
    in-progress attempt in a *different* scope (e.g. the student's own solo
    attempt when this call is an ops cohort-assign, or vice versa) is never
    resumed — it's left alone and a fresh attempt is minted in the
    requested scope instead (2026-08-22 fix; see the inline comment on the
    resume query for the bug this closes).

    `force_new=True` skips the resume and always mints a new attempt, even
    with another already `in_progress` — the design mission's "run several
    named CubeSat designs at once" flow (2026-08-15) opts into this; every
    other caller leaves it `False` and keeps the original single-flight
    behavior unchanged.

    `cohort_id` (2026-08-17) is resolved by the caller — `resolve_student_
    cohort()` above for a solo attempt, `Team.cohort_id` for a team
    one — and frozen onto the new attempt at creation. Not re-resolved on a
    resume: an attempt already in progress keeps whatever cohort it started
    with, same reasoning `variant_id` already gets on resume (finish what
    you started, don't silently reattribute it).
    """
    if (user_id is None) == (team_id is None):
        raise HTTPException(400, detail="Exactly one of user_id or team_id is required")
    owner_column = MissionAttempt.user_id if user_id is not None else MissionAttempt.team_id
    owner_value = user_id if user_id is not None else team_id

    if not force_new:
        # Cross-scope resume bug (found 2026-08-22, live-tested): without
        # this cohort_id match, a student's own independent in-progress
        # attempt (cohort_id=None) got silently handed back to an
        # ops-assign call requesting a cohort-scoped run — and the reverse,
        # a student's own "start attempt" resuming a cohort-controlled run
        # that happened to still be in progress. Resuming must only ever
        # find an attempt already in the exact scope being asked for; a
        # scope mismatch means mint a fresh one instead (below), leaving
        # the mismatched attempt untouched and independently resumable.
        cohort_match = (
            MissionAttempt.cohort_id == cohort_id if cohort_id is not None
            else MissionAttempt.cohort_id.is_(None)
        )
        existing = await db.scalar(
            select(MissionAttempt)
            .where(
                MissionAttempt.mission_id == mission_id,
                owner_column == owner_value,
                MissionAttempt.status == "in_progress",
                cohort_match,
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
        team_id=team_id,
        attempt_no=(max_no or 0) + 1,
        status="in_progress",
        cohort_id=cohort_id,
    )
    db.add(attempt)
    await db.flush()

    if team_id is not None:
        for member_id in await team_member_ids(db, team_id=team_id):
            db.add(MissionAttemptMember(attempt_id=attempt.id, user_id=member_id))
        await db.flush()

    return attempt


async def assign_mission_run(
    db: AsyncSession, *, mission_id: uuid.UUID, user_id: uuid.UUID, cohort_id: uuid.UUID,
    variant_id: uuid.UUID | None = None, force_new: bool = False,
) -> MissionAttempt:
    """Ops-only cohort-scoped run (2026-08-21, LMS Program redesign) — the
    ONLY way a solo attempt gets a `cohort_id` now that
    `start_mission_attempt` (routers/missions/student.py) no longer
    auto-resolves one from the student's registration. Used both by the
    admin `POST /missions/admin/attempts/assign` endpoint directly and by
    `services/lms/program.py::assign_lms_program` for a checklist's
    `mission_run` items — deliberately not program-exclusive, so a cohort
    that just needs scoped missions (no full program checklist, e.g. TDRA)
    can use this the same way.

    `variant_id=None` resolves to the mission's easiest variant (lowest
    `position`) — most missions only need one; callers that care pass one
    explicitly."""
    if variant_id is None:
        variant_id = await db.scalar(
            select(MissionVariant.id)
            .where(MissionVariant.mission_id == mission_id)
            .order_by(MissionVariant.position)
            .limit(1)
        )
        if variant_id is None:
            raise HTTPException(status_code=404, detail="Mission has no variants")
    return await start_attempt(
        db, mission_id=mission_id, variant_id=variant_id, user_id=user_id,
        cohort_id=cohort_id, force_new=force_new,
    )


async def _attempt_recipients(db: AsyncSession, attempt: MissionAttempt) -> list[uuid.UUID]:
    """Who a passing attempt owes points/completion to: the solo student,
    or (P6-3) every member of the `mission_attempt_members` snapshot frozen
    at `start_attempt` time — never the live `TeamMember` roster, which
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
        if attempt.team_id is not None:
            ref["team_id"] = str(attempt.team_id)
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
