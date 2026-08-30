"""Group pre-existing single-session open calls into a standing CohortCall
(2026-08-30).

`staffing.open_call`/`reopen` now auto-attach a session's own call to a
cohort-wide CohortCall the moment it's opened (found-or-created by matching
audience) — see the module docstring on `_find_or_create_open_cohort_call`.
That only takes effect going forward: any `SessionCall` that was already
open *before* this change shipped has `cohort_call_id IS NULL` and keeps
showing on the instructor's "Available Work" page under the old, separate
"Single sessions" list until it's closed and reopened — or backfilled here.

USAGE
    python -m scripts.backfill_group_open_session_calls [--dry-run]

IDEMPOTENCY
    Only ever touches SessionCall rows that are currently `status="open"`
    and `cohort_call_id IS NULL` — a call already grouped (by this script or
    by the live code) is never revisited. Safe to run more than once, and
    safe to run while the app is live (same find-or-create logic the app
    itself uses for every new open_call).
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.session import Session, SessionCallTarget
from app.models.sessions.session_call import SessionCall
from app.services.sessions.staffing import _find_or_create_open_cohort_call


async def backfill_group_open_session_calls(db: AsyncSession) -> int:
    """Attaches every open, ungrouped SessionCall to a (found-or-created)
    CohortCall for its session's cohort. Returns the number of calls
    grouped. Pure service function: flushes but never commits/rolls back —
    that's the caller's job, same convention as the other backfill scripts
    in this directory."""
    ungrouped = (await db.execute(
        select(SessionCall).where(SessionCall.status == "open", SessionCall.cohort_call_id.is_(None))
    )).scalars().all()

    grouped = 0
    for call in ungrouped:
        session = await db.get(Session, call.session_id)
        if session is None:
            continue
        target_user_ids = list((await db.execute(
            select(SessionCallTarget.user_id).where(SessionCallTarget.call_id == call.id)
        )).scalars().all())

        cohort_call = await _find_or_create_open_cohort_call(
            db, cohort_id=session.cohort_id, target_user_ids=target_user_ids,
            actor_user_id=call.created_by, label=call.label,
        )
        call.cohort_call_id = cohort_call.id
        grouped += 1

    await db.flush()
    return grouped


async def run(dry_run: bool = False) -> int:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        grouped = await backfill_group_open_session_calls(db)
        if dry_run:
            await db.rollback()
            print(f"[backfill_group_open_session_calls] DRY RUN — would group {grouped} call(s); no changes written.")
        else:
            await db.commit()
            print(f"[backfill_group_open_session_calls] grouped {grouped} call(s) into a cohort call.")
    return grouped


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="Report what would happen; write nothing.")
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
