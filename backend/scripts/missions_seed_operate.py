"""Seed the "Flight Operations" mission — the ONE `missions` row and its
three difficulty variants (Operate v2, Stage 7C).

    python scripts/missions_seed_operate.py [--dry-run] [--update]

Same idempotent-reference-data pattern as `missions_seed_design.py` and
`seed_inventory.py` — not a migration, safe to re-run, skips anything
already present by slug/position. `--update` additionally rewrites the
config of variants that already exist, which is what you want when
retuning difficulty against a dev database.

**How difficulty works here.** Not different mechanics — the same orbit,
the same vehicle model, the same seven-fault library. What changes is:

* how many orbits you fly, and therefore how many passes you get,
* how much margin the vehicle has (battery size, how fast the wheel loads up),
* how many external faults are injected, and whether their timing is fixed
  or reshuffled per attempt (D-b),
* how much of the Ops Handbook is written down for you (D-d),
* how demanding the mission objective is.

D-b: Cadet is deliberately **fixed** — a retry drills the same scenario,
which is legitimate training for someone still learning the console.
Engineer and above **shuffle** which orbit each injected fault lands on,
seeded per attempt, so a second run is a flight rather than a memory test.

D-f: `crew_concurrency` compresses the injected faults onto one orbit for
team attempts, so five officers have five things happening at once instead
of four of them watching the fifth work.
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

MISSION_SLUG = "operate-your-satellite"  # unchanged — v1 attempts keep working

SUMMARY = (
    "Fly a 3U CubeSat through a real orbit. Watch the power balance through eclipse, "
    "catch faults from the telemetry before they cost you a pass, and get your science "
    "on the ground in the eight minutes a day the ground station can hear you."
)

DESCRIPTION = (
    "A ground-station console for a satellite in a 550 km sun-synchronous orbit. The "
    "spacecraft is genuinely simulated: the battery charges in sunlight and drains in "
    "shadow, the reaction wheel loads up with momentum until you dump it, mass memory "
    "fills faster than you can downlink it, and the processor takes radiation hits over "
    "the South Atlantic Anomaly.\n\n"
    "Nothing tells you what is wrong. The telemetry shows you a symptom and the Ops "
    "Handbook tells you what symptoms mean — working out which fault you are looking at, "
    "and reaching for the right command before the consequence lands, is the mission.\n\n"
    "Fly it solo, or as a crew with an officer on each subsystem."
)


VARIANTS = [
    dict(
        label="Cadet", position=1, points=100,
        config=dict(
            pass_threshold=50,
            handbook_disclosure="full",       # symptom, meaning, action, consequence
            shuffle_faults=False,             # D-b: fixed, so a retry drills the same flight
            crew_concurrency=False,
            injected_faults=["seu"],
            orbit=dict(orbits=2, time_compression=16.0),
            spacecraft=dict(
                battery_capacity_wh=26.0,     # generous margin — power is survivable here
                solar_array_w=6.5,
                wheel_accum_rpm_per_s=0.22,
            ),
            objectives=dict(science_takes=2, downlink_mb=40, soc_floor=0.30),
        ),
    ),
    dict(
        label="Engineer", position=2, points=200,
        config=dict(
            pass_threshold=65,
            handbook_disclosure="symptoms",   # what it looks like and why; you pick the response
            shuffle_faults=True,
            crew_concurrency=True,
            injected_faults=["seu", "beacon_lock"],
            orbit=dict(orbits=3, time_compression=18.0),
            spacecraft=dict(),                # the standard vehicle
            objectives=dict(science_takes=3, downlink_mb=60, soc_floor=0.40),
        ),
    ),
    dict(
        label="Flight Director", position=3, points=350,
        config=dict(
            pass_threshold=75,
            handbook_disclosure="reference",  # the fault exists; you are the flight director
            shuffle_faults=True,
            crew_concurrency=True,
            # Two upsets. Ignore the first and the processor latches up — which is the
            # one situation where REBOOT_OBC is the correct command rather than the
            # punished one. That conditional rule is the best teaching moment in the set.
            injected_faults=["seu", "beacon_lock", "seu"],
            # Stage 7C-9: fly the satellite you designed. Falls back to the
            # standard vehicle for anyone without a passed design attempt,
            # so this never blocks the mission — it just makes the design
            # mission's power margin something you have to live with.
            spacecraft_source="design",
            orbit=dict(orbits=4, time_compression=20.0),
            spacecraft=dict(
                battery_capacity_wh=18.0,
                solar_array_w=5.0,
                wheel_accum_rpm_per_s=0.34,
                storage_capacity_mb=100.0,
            ),
            objectives=dict(science_takes=4, downlink_mb=80, soc_floor=0.45),
        ),
    ),
]


async def seed(db: AsyncSession, *, dry_run: bool, update: bool) -> None:
    created = {"mission": 0, "variants": 0}
    skipped = {"mission": 0, "variants": 0}
    updated = {"mission": 0, "variants": 0}

    author = (await db.execute(select(User).where(User.roles.contains(["operations"])))).scalars().first()
    if author is None:
        print("No 'operations' user found — cannot set missions.authored_by. Create one first.")
        return

    mission = (await db.execute(select(Mission).where(Mission.slug == MISSION_SLUG))).scalars().first()
    if mission is None:
        mission = Mission(
            id=uuid.uuid4(), title="Flight Operations", slug=MISSION_SLUG,
            summary=SUMMARY, description=DESCRIPTION,
            kind="operate", team_policy="either", status="published", access_mode="open",
            authored_by=author.id, track="Spacecraft systems",
        )
        db.add(mission)
        created["mission"] += 1
        await db.flush()
    elif update:
        mission.title = "Flight Operations"
        mission.summary = SUMMARY
        mission.description = DESCRIPTION
        updated["mission"] += 1
    else:
        skipped["mission"] += 1

    for v in VARIANTS:
        existing = (await db.execute(select(MissionVariant).where(
            MissionVariant.mission_id == mission.id, MissionVariant.position == v["position"],
        ))).scalars().first()
        if existing is not None:
            if update:
                existing.label = v["label"]
                existing.points = v["points"]
                existing.config = v["config"]
                updated["variants"] += 1
            else:
                skipped["variants"] += 1
            continue
        db.add(MissionVariant(id=uuid.uuid4(), mission_id=mission.id, **v))
        created["variants"] += 1
    await db.flush()

    for label in created:
        print(f"{label:12} created {created[label]:3}   updated {updated[label]:3}   unchanged {skipped[label]:3}")

    if dry_run:
        print("\n--dry-run: rolling back, nothing written.")
    else:
        await db.commit()
        print(f"\nCommitted. Mission slug: {MISSION_SLUG}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report what would change, write nothing")
    parser.add_argument("--update", action="store_true", help="Rewrite existing mission/variant content too")
    args = parser.parse_args()

    engine = create_async_engine(settings.DATABASE_URL)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as db:
        await seed(db, dry_run=args.dry_run, update=args.update)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
