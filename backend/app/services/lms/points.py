"""LMS points award service (P2-2, Phase 2 Stage 2, 2026-08-10).

⚠️ Unrelated to `services/points.py` (ambassadors, keyed on `ambassador_id`)
and `pages/ambassadors/AmbassadorLeaderboard.tsx` — different population,
do not reuse either.

`award_points` is the one choke point every award goes through — append-
only, written at the moment of award, never recomputed. Nothing else in
this codebase should insert a `point_events` row directly.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.points import PointEvent

# ── award rules (P2-6) — the only place a point value is a literal; change
# "a quiz pass is worth 50" here, not by hunting for the number elsewhere ──
QUIZ_PASS_POINTS = 50
# Scaled down, not zeroed — using live per-question feedback is legitimate
# (D7, the operator asked for it deliberately); it just shouldn't top the
# leaderboard the same way a clean first attempt does.
QUIZ_PASS_POINTS_WITH_HINTS = 20


async def award_points(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    source: str,
    points: int,
    idempotency_key: str,
    ref: dict | None = None,
) -> PointEvent | None:
    """Insert one point_events row. Returns None (never raises) if
    `idempotency_key` was already used for this `user_id`+`source` — a
    replay is a no-op by constraint, the same discipline `enroll()`/
    `register()` already use everywhere in this codebase.

    A Core `insert()` executed directly inside the SAVEPOINT — not
    `db.add()` + `flush()` — same shape `merge_contacts`'s per-row conflict
    handling already uses (services/spine/identity.py). Unlike `register()`'s
    equivalent SAVEPOINT (services/sessions/registration.py), a conflict
    here must NOT propagate: the caller (e.g. `submit_quiz`) needs to keep
    using the session afterward, and an ORM-tracked pending object left
    over from a failed `flush()` gets retried on the session's next
    autoflush and raises the same IntegrityError again, uncaught — a Core
    statement never enters the identity map in the first place, so there's
    nothing left to retry."""
    if points <= 0:
        return None
    event_id = uuid.uuid4()
    stmt = insert(PointEvent).values(
        id=event_id, user_id=user_id, source=source, points=points,
        ref=ref, idempotency_key=idempotency_key,
    )
    try:
        async with db.begin_nested():
            await db.execute(stmt)
    except IntegrityError:
        return None
    return await db.get(PointEvent, event_id)


async def reverse_points(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    source: str,
    points: int,
    idempotency_key: str,
    ref: dict | None = None,
) -> PointEvent | None:
    """The reversal sibling of `award_points` (Live Games Phase 2C, 8-7/8-9,
    D15/D16/D17) — a new offsetting ledger row, same append-only, never-
    delete-the-original discipline; the original award row is untouched.
    `points` is the positive magnitude to take back; this writes `-points`.

    `award_points` itself refuses `points <= 0`, so it can't mint this row
    — hence a sibling rather than a call with a negative amount. Callers
    must pick an `idempotency_key` distinct from the original award's (the
    unique constraint is per `user_id`+`source`, and the original row is
    never deleted) — the games reversal callers use `f"{original_key}:reversal"`.
    """
    if points <= 0:
        return None
    event_id = uuid.uuid4()
    stmt = insert(PointEvent).values(
        id=event_id, user_id=user_id, source=source, points=-points,
        ref=ref, idempotency_key=idempotency_key,
    )
    try:
        async with db.begin_nested():
            await db.execute(stmt)
    except IntegrityError:
        return None
    return await db.get(PointEvent, event_id)


async def award_quiz_points(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    item_id: uuid.UUID,
    first_score: Decimal,
    hints_used_at_first_submit: int,
    pass_threshold: int,
) -> PointEvent | None:
    """Quiz-specific award rule. Called exactly once, by `submit_quiz`, at
    the moment `item_progress.first_score` is written for the first time —
    `first_score` being NULL-until-now is itself the guard against a second
    call for the same item.

    Points only for a first attempt that actually passed. A later retry
    passing does not retroactively earn them: keying strictly on the first
    submission is what closes the `submit(garbage) -> read the leaked
    answers -> submit(correct)` path (audit §9.2) — scaling the award by
    `hints_used` alone doesn't, because that path never touches `check`.

    Scope note (audit §9.2): this makes points fair, not `best_score` a
    trustworthy measure of knowledge — a genuinely unprepared student who
    fails attempt one and studies before passing on a retry earns zero
    points for this item. That's the deliberate trade for competitive
    integrity, not an oversight; worth knowing before a certificate or
    other feature keys off quiz scores.
    """
    passed_first_try = pass_threshold == 0 or float(first_score) >= pass_threshold
    if not passed_first_try:
        return None
    points = QUIZ_PASS_POINTS if hints_used_at_first_submit == 0 else QUIZ_PASS_POINTS_WITH_HINTS
    return await award_points(
        db, user_id=user_id, source="quiz", points=points,
        idempotency_key=str(item_id),
        ref={"item_id": str(item_id), "hints_used": hints_used_at_first_submit},
    )
