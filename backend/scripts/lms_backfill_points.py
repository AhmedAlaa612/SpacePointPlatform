"""Backfill point_events for quiz passes that predate the points ledger —
P2-5, LMS Phase 2 Stage 2.

Every `item_progress` row for a passed quiz item, written before P2-3
shipped, has `first_score IS NULL` (the column didn't exist yet) — that is
exactly the marker this script uses to find them; a row the live code has
already scored (post-fix) is never touched here. For each: `first_score` is
backfilled from `best_score` (the true first-attempt score for old data is
gone — `best_score` is the closest available proxy) and a `point_events` row
is minted with `source='migration'`, visibly distinct from a live 'quiz'
award, at the same full `QUIZ_PASS_POINTS` rate (no `hints_used` scaling —
that data doesn't exist for these rows either, and assuming the more
generous rate is the fairer default for a backfill nobody can dispute
question-by-question).

Scope note, deliberately NOT built here: the plan also says "and course
completions" — this script does not award a separate course-completion
bonus. No point value for one is defined anywhere in the plan's schema or
award-rules module (services/lms/points.py), and inventing one isn't this
script's call to make; ask the operator before adding it; quiz-pass points
already flow into a student's total either way.

USAGE
    python -m scripts.lms_backfill_points [--dry-run]

IDEMPOTENCY
    Safe to re-run: award_points is idempotent on (user_id, source,
    idempotency_key), and first_score being backfilled (no longer NULL) is
    itself why a row is skipped on a second pass.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.course import ModuleItem
from app.models.lms.enrollment import ItemProgress
from app.services.lms.points import QUIZ_PASS_POINTS, award_points


async def backfill_quiz_points(db: AsyncSession) -> int:
    """Mints one migration-sourced point_events row per pre-existing passed
    quiz. Pure service function: flushes but never commits — that's the
    caller's job (run() below, or the `db` test fixture's rollback in
    tests). Returns the number of awards actually minted."""
    rows = (await db.execute(
        select(ItemProgress, ModuleItem)
        .join(ModuleItem, ModuleItem.id == ItemProgress.item_id)
        .where(
            ModuleItem.kind == "quiz",
            ItemProgress.status == "completed",
            ItemProgress.first_score.is_(None),
        )
    )).all()

    awarded = 0
    for progress, _item in rows:
        progress.first_score = progress.best_score
        progress.first_scored_at = progress.completed_at or datetime.now(timezone.utc)

        event = await award_points(
            db, user_id=progress.user_id, source="migration", points=QUIZ_PASS_POINTS,
            idempotency_key=str(progress.item_id),
            ref={"item_id": str(progress.item_id), "backfilled_from": "best_score"},
        )
        if event is not None:
            awarded += 1

    await db.flush()
    return awarded


async def run(dry_run: bool = False) -> int:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        awarded = await backfill_quiz_points(db)
        if dry_run:
            await db.rollback()
            print(f"[lms_backfill_points] DRY RUN — would award {awarded} migration point_events row(s); "
                  f"no changes written.")
        else:
            await db.commit()
            print(f"[lms_backfill_points] awarded {awarded} migration point_events row(s).")
    return awarded


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Report what would happen; write nothing.")
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
