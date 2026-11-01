"""Generate and seed realistic satellite module hardware datasheets (PDFs)
into storage_local and database for the SpacePoint Instructor Readiness Pipeline.
"""

import asyncio
import sys
from pathlib import Path

# Add backend directory to sys.path so 'app' can be resolved
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import AsyncSessionLocal
from app.services.sessions.datasheet_seeder import ensure_default_datasheets_seeded


async def main() -> None:
    print("Seeding hardware datasheets (generating PDFs and database entries)...")
    async with AsyncSessionLocal() as db:
        count = await ensure_default_datasheets_seeded(db)
        print(f"Finished seeding: {count} new datasheets created/updated.")


if __name__ == "__main__":
    asyncio.run(main())
