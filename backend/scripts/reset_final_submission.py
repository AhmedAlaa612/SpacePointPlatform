"""Reset final submission lock for a team, and optionally reset checklist items to test the full flow."""
import argparse
import asyncio
import sys
from pathlib import Path

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select, update
from app.db.session import AsyncSessionLocal
from app.models.team import Team, TeamMember
from app.models.lms.program import LmsProgramAssignment, LmsProgramItemProgress, LmsProgramTeamItemProgress


async def main():
    parser = argparse.ArgumentParser(description="Reset team final submission lock")
    parser.add_argument("--team", default="edes", help="Team name (default: edes)")
    parser.add_argument("--reset-tasks", action="store_true", help="Also reset tasks back to pending (to test Step 1)")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Team).where(Team.name == args.team))
        team = res.scalar_one_or_none()
        if not team:
            print(f"❌ Error: Team '{args.team}' not found.")
            return

        print(f"Found team '{team.name}' (ID: {team.id})")
        print(f"Current final_locked_at: {team.final_locked_at}")

        # 1. Clear submission lock
        team.final_locked_at = None
        team.final_locked_by = None
        print("✓ Unlocked final submission gate (final_locked_at = NULL)")

        # 2. Optionally reset checklist tasks back to 'pending'
        if args.reset_tasks:
            # Reset team-scoped tasks (where team deliverables live!)
            team_items_res = await db.execute(
                update(LmsProgramTeamItemProgress)
                .where(LmsProgramTeamItemProgress.team_id == team.id)
                .values(status="pending", completed_at=None, submitted_url=None, submitted_text=None)
            )
            print(f"✓ Reset {team_items_res.rowcount} team checklist task(s) to 'pending'")

            # Also reset individual tasks for members
            mem_res = await db.execute(select(TeamMember.user_id).where(TeamMember.team_id == team.id))
            user_ids = mem_res.scalars().all()

            if user_ids:
                assign_res = await db.execute(
                    select(LmsProgramAssignment.id).where(LmsProgramAssignment.user_id.in_(user_ids))
                )
                assignment_ids = assign_res.scalars().all()

                if assignment_ids:
                    await db.execute(
                        update(LmsProgramItemProgress)
                        .where(LmsProgramItemProgress.assignment_id.in_(assignment_ids))
                        .values(status="pending", completed_at=None, submitted_url=None, submitted_text=None)
                    )
                    print(f"✓ Reset individual task progress across {len(assignment_ids)} assignment(s)")

        await db.commit()
        print("\n✨ Done! Refresh the roadmap page in your browser to test the flow.")


if __name__ == "__main__":
    asyncio.run(main())
