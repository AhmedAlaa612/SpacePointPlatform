"""Seed the Ground Station mission — one `missions` row (`kind='ground_station'`,
`team_policy='either'`) and one variant. No scoring: `points=0`, and there's
no verifier for this kind — an attempt just tracks who owns which rig
(see routers/ground_station/attempts.py). Idempotent (skips if the slug
already exists).

    python scripts/seed_ground_station_mission.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.missions.mission import Mission, MissionVariant  # noqa: E402
from app.models.user import User  # noqa: E402

SLUG = "ground-station"


async def main() -> None:
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(Mission).where(Mission.slug == SLUG))).scalars().first()
        if existing:
            print(f"already exists: {existing.id}")
            return

        admin = (await db.execute(
            select(User).where(User.roles.any("admin")).limit(1)
        )).scalars().first()
        if admin is None:
            raise SystemExit("No admin user found — seed an admin first")

        mission = Mission(
            id=uuid.uuid4(),
            title="Ground Station",
            slug=SLUG,
            summary="Connect your ESP32 ground station rig and stream live telemetry.",
            description=(
                "Wire up your ESP32 and its sensors (temperature, power, MPU6050/9250 "
                "orientation) and watch it live — real-time charts, attitude, orbit "
                "tracking, and a command console. Run it solo or as a team."
            ),
            kind="ground_station",
            team_policy="either",
            status="published",
            access_mode="open",
            authored_by=admin.id,
        )
        db.add(mission)
        await db.flush()

        db.add(MissionVariant(
            id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=0, config={},
        ))
        await db.commit()
        print(f"created: {mission.id}")


if __name__ == "__main__":
    asyncio.run(main())
