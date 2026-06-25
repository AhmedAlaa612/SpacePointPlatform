"""Seed the Phase-1 curriculum checklist from the source app's seed_data.json.

    python seed_instructors.py

Idempotent: skips modules that already exist (matched by title).
"""

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.instructors.checklist import ChecklistItem, ChecklistModule, ModuleSection

SEED_PATH = Path(__file__).resolve().parents[2] / "instructors" / "seed_data.json"


async def seed_checklist() -> None:
    modules_data = json.loads(SEED_PATH.read_text(encoding="utf-8"))

    async with AsyncSessionLocal() as db:
        for mod in modules_data:
            existing = (
                await db.execute(select(ChecklistModule).where(ChecklistModule.title == mod["module_title"]))
            ).scalars().first()
            if existing:
                print(f"OK - module already seeded: {mod['module_title']}")
                continue

            module = ChecklistModule(title=mod["module_title"], sort_order=mod["sort_order"])
            db.add(module)
            await db.flush()  # assign module.id

            for sec in mod["sections"]:
                section_id = None
                if sec.get("section_title"):
                    section = ModuleSection(
                        module_id=module.id, title=sec["section_title"], sort_order=sec["sort_order"]
                    )
                    db.add(section)
                    await db.flush()
                    section_id = section.id

                for item in sec["items"]:
                    db.add(
                        ChecklistItem(
                            module_id=module.id,
                            section_id=section_id,
                            item_code=item["item_code"],
                            title=item["title"],
                            description=item.get("description"),
                            sort_order=item["sort_order"],
                        )
                    )

            await db.commit()
            print(f"OK - seeded module: {mod['module_title']}")


async def main() -> None:
    await seed_checklist()


if __name__ == "__main__":
    asyncio.run(main())
