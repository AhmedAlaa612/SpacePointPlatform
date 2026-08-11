"""Seed the "Operate Your Satellite" mission — the ONE `missions` row and
its three difficulty variants (Phase 2B, Stage 7B-3).

    python scripts/missions_seed_operate.py [--dry-run]

Same idempotent-reference-data pattern as `missions_seed_design.py` and
`seed_inventory.py` — not a migration, safe to re-run, skips anything
already present by slug/position.

Each variant's `config.anomalies` is the deterministic script
`services/missions/operate/evaluator.py::evaluate_operation` reads:
subsystem health fails after N commands, resolved only by that
subsystem's specific fix command (`services/missions/operate/commands.py
::FIX_COMMAND_SUBSYSTEM`). Difficulty is spacing + count + how forgiving
the pass threshold is, not different mechanics.
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.missions.mission import Mission, MissionVariant  # noqa: E402
from app.models.user import User  # noqa: E402

MISSION_SLUG = "operate-your-satellite"

VARIANTS = [
    dict(
        label="Cadet", position=1, points=100,
        config=dict(
            pass_threshold=50,
            anomalies=[
                {"trigger_after_commands": 3, "subsystem": "EPS", "correct_command": "EPS_RECONFIG"},
                {"trigger_after_commands": 6, "subsystem": "CDHS", "correct_command": "RESET_WDT"},
            ],
        ),
    ),
    dict(
        label="Engineer", position=2, points=200,
        config=dict(
            pass_threshold=67,
            anomalies=[
                {"trigger_after_commands": 2, "subsystem": "EPS", "correct_command": "EPS_RECONFIG"},
                {"trigger_after_commands": 4, "subsystem": "COMMS", "correct_command": "UPDATE_BEACON"},
                {"trigger_after_commands": 6, "subsystem": "ADCS", "correct_command": "ADCS_RECALIBRATE"},
            ],
        ),
    ),
    dict(
        label="Flight Director", position=3, points=350,
        config=dict(
            pass_threshold=80,
            anomalies=[
                {"trigger_after_commands": 1, "subsystem": "EPS", "correct_command": "EPS_RECONFIG"},
                {"trigger_after_commands": 2, "subsystem": "CDHS", "correct_command": "RESET_WDT"},
                {"trigger_after_commands": 3, "subsystem": "ADCS", "correct_command": "ADCS_RECALIBRATE"},
                {"trigger_after_commands": 4, "subsystem": "COMMS", "correct_command": "UPDATE_BEACON"},
                {"trigger_after_commands": 5, "subsystem": "PAYLOAD", "correct_command": "PAYLOAD_RESET"},
            ],
        ),
    ),
]


async def seed(db: AsyncSession, *, dry_run: bool) -> None:
    created = {"mission": 0, "variants": 0}
    skipped = {"mission": 0, "variants": 0}

    author = (await db.execute(select(User).where(User.roles.contains(["operations"])))).scalars().first()
    if author is None:
        print("No 'operations' user found — cannot set missions.authored_by. Create one first.")
        return

    mission = (await db.execute(select(Mission).where(Mission.slug == MISSION_SLUG))).scalars().first()
    if mission is None:
        mission = Mission(
            id=uuid.uuid4(), title="Operate Your Satellite", slug=MISSION_SLUG,
            summary="Fly the satellite you designed: watch live telemetry, issue telecommands, "
                     "and respond when a subsystem fails.",
            description="A ground-station simulator ported from an intern's SatKit prototype. "
                         "Subsystems fail on their own schedule — the only warning is what the "
                         "telemetry and the terminal tell you. Solo or as a crew.",
            kind="operate", team_policy="either", status="published", access_mode="open",
            authored_by=author.id, track="Spacecraft systems",
        )
        db.add(mission)
        created["mission"] += 1
        await db.flush()
    else:
        skipped["mission"] += 1

    for v in VARIANTS:
        existing = (await db.execute(select(MissionVariant).where(
            MissionVariant.mission_id == mission.id, MissionVariant.position == v["position"],
        ))).scalars().first()
        if existing is not None:
            skipped["variants"] += 1
            continue
        db.add(MissionVariant(id=uuid.uuid4(), mission_id=mission.id, **v))
        created["variants"] += 1
    await db.flush()

    for label in created:
        print(f"{label:12} created {created[label]:3}   already present {skipped[label]:3}")

    if dry_run:
        print("\n--dry-run: rolling back, nothing written.")
    else:
        await db.commit()
        print(f"\nCommitted. Mission slug: {MISSION_SLUG}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would change, write nothing")
    args = parser.parse_args()

    engine = create_async_engine(settings.DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        await seed(db, dry_run=args.dry_run)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
