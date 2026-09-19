"""One-off repair: wire up team-scoped `mission_run` checklist items for
teams that were formed BEFORE those items were added to their cohort's
checklist.

The gap this fixes (found live, 2026-09-19): `sync_assignment_items` — what
the "Resync students" button ultimately calls — only reaches
`_assign_team_mission_run` for items whose INDIVIDUAL progress row is
missing:

    missing = [item for item in items if item.id not in existing_item_ids]
    if not missing:
        return 0
    for item in missing:
        ...
        if item.scope == "team":
            await _assign_team_mission_run(...)

So once every teammate already holds their individual placeholder row for a
team-scoped mission_run item (which is the normal state — the placeholder is
created the moment they're assigned), the item is never "missing", the team
branch never runs, and the team never gets its shared
`LmsProgramTeamItemProgress` row or its `MissionAttempt`. The checklist tile
then has no `mission_attempt_id` to navigate to, so clicking "Open" silently
does nothing. Re-clicking Resync can never fix it: the endpoint honestly
reports `items_added: 0` every time.

`sync_team_mission_runs` reads the team-scoped mission_run items straight off
the team's cohort and is immune to that gate, so it repairs the state. It's
idempotent — a no-op for every item that already has its attempt.

Usage (repair one team, or every team in a cohort):

    python scripts/lms_fix_team_mission_runs.py --team <team_uuid> --dry-run
    python scripts/lms_fix_team_mission_runs.py --team <team_uuid>
    python scripts/lms_fix_team_mission_runs.py --cohort <cohort_uuid>

Always run once with --dry-run first: it does the identical work and prints
the identical report, then rolls back instead of committing.
"""
import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.lms.program import LmsProgramItem, LmsProgramTeamItemProgress
from app.models.team import Team
from app.services.lms.program import effective_cohort_program_items, sync_team_mission_runs


async def _state(db, team: Team) -> dict[uuid.UUID, uuid.UUID | None]:
    """item_id -> mission_attempt_id (None when the team row exists but is
    unwired; the key is absent entirely when there's no team row at all)."""
    rows = (await db.execute(
        select(LmsProgramTeamItemProgress.item_id, LmsProgramTeamItemProgress.mission_attempt_id)
        .join(LmsProgramItem, LmsProgramItem.id == LmsProgramTeamItemProgress.item_id)
        .where(
            LmsProgramTeamItemProgress.team_id == team.id,
            LmsProgramItem.item_type == "mission_run",
            LmsProgramItem.scope == "team",
        )
    )).all()
    return {item_id: attempt_id for item_id, attempt_id in rows}


async def _team_run_items(db, team: Team) -> list[LmsProgramItem]:
    if team.cohort_id is None:
        return []
    resolved = await effective_cohort_program_items(db, team.cohort_id)
    if resolved is None:
        return []
    _, items, _ = resolved
    return [i for i in items if i.item_type == "mission_run" and i.scope == "team" and i.mission_id]


async def main():
    ap = argparse.ArgumentParser(description="Repair unwired team-scoped mission_run checklist items")
    target = ap.add_mutually_exclusive_group(required=True)
    target.add_argument("--team", help="Single team uuid to repair")
    target.add_argument("--cohort", help="Repair every team in this cohort uuid")
    ap.add_argument("--dry-run", action="store_true", help="Do the work, print the report, then roll back")
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        if args.team:
            team = await db.get(Team, uuid.UUID(args.team))
            if team is None:
                print(f"Team {args.team} not found.")
                return
            teams = [team]
        else:
            teams = list((await db.execute(
                select(Team).where(Team.cohort_id == uuid.UUID(args.cohort)).order_by(Team.name)
            )).scalars().all())
            if not teams:
                print(f"No teams in cohort {args.cohort}.")
                return

        total_repaired = 0
        for team in teams:
            items = await _team_run_items(db, team)
            if not items:
                print(f"\n{team.name} ({team.id}): no team-scoped mission_run items — skipped.")
                continue

            before = await _state(db, team)
            await sync_team_mission_runs(db, team=team)
            after = await _state(db, team)

            print(f"\n{team.name} ({team.id}):")
            repaired = 0
            for item in sorted(items, key=lambda i: i.position):
                was, now = before.get(item.id), after.get(item.id)
                if was is not None:
                    print(f"  pos {item.position:>3}  {item.title[:44]:<44} already wired ({was})")
                elif now is not None:
                    print(f"  pos {item.position:>3}  {item.title[:44]:<44} REPAIRED -> {now}")
                    repaired += 1
                else:
                    print(f"  pos {item.position:>3}  {item.title[:44]:<44} STILL UNWIRED (no team members?)")
            print(f"  repaired {repaired} of {len(items)} item(s)")
            total_repaired += repaired

        if args.dry_run:
            await db.rollback()
            print(f"\n[DRY RUN] {total_repaired} item(s) would be repaired. Rolled back, nothing written.")
        else:
            await db.commit()
            print(f"\nCommitted. {total_repaired} item(s) repaired.")


if __name__ == "__main__":
    asyncio.run(main())
