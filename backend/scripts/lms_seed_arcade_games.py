"""Seed all 51 SpacePoint Mission Arcade games into `arcade_games`.

Usage:
    python -m scripts.lms_seed_arcade_games [--update]
"""

import argparse
import asyncio

from app.db.session import AsyncSessionLocal
from app.services.lms.arcade import ensure_arcade_games_seeded
from app.services.lms.arcade_data import ARCADE_GAMES


async def seed(update: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        seeded = await ensure_arcade_games_seeded(db, force=update)
        print(f"Arcade seed complete: {seeded} records processed (catalog total: {len(ARCADE_GAMES)} games).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="Update existing rows in-place")
    args = parser.parse_args()
    asyncio.run(seed(update=args.update))
