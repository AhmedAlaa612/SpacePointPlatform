"""Seed inventory reference data — locations, the component catalogue, and the
SatKit bill of materials (I1-5).

    python scripts/seed_inventory.py [--dry-run]

**This is a starting point, not truth.** The quantities and categories below
are transcribed from the legacy inventory app's `REQUIRED_COUNTS`
(backend/routers/cubesats.py), which is the only written record of what a
SatKit contains — but nobody has checked it against a real box in months, and
the legacy schema had already been hand-edited twice. Expect to correct it in
the UI. Correcting 27 quantities is a great deal faster than typing 27
component names, which is the only reason this exists.

Idempotent: re-running skips anything already present by name/code, so it is
safe to run again after adding a location or an item by hand. It never edits
or deletes anything that already exists — if a quantity here disagrees with
what is in the database, the database wins and this script says so.

Deliberately NOT a migration. Reference data is somebody's decision, not
schema, and it must not be re-applied silently on every deploy.
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
from app.models.inventory import Item, KitTemplate, KitTemplateItem, Location  # noqa: E402

# ── locations ───────────────────────────────────────────────────────────────
# Operator-confirmed 2026-07-29: "Main" is a separate UAE warehouse, not one of
# the three hubs. The hubs are where instructors collect and return.
LOCATIONS = [
    ("Main Warehouse", "AE"),
    ("Dubai", "AE"),
    ("Abu Dhabi", "AE"),
    ("Al Ain", "AE"),
    ("Egypt", "EG"),
]

# ── the SatKit bill of materials ────────────────────────────────────────────
# (display name, category, required qty)
SATKIT_BOM = [
    ("Structures",                  "mechanical", 6),
    ("Current Sensor",              "sensor",     1),
    ("Temperature Sensor",          "sensor",     1),
    ("FRAM",                        "board",      1),
    ("SD Card",                     "board",      1),
    ("Reaction Wheel",              "other",      1),
    ("MPU-9250",                    "sensor",     1),
    ("GPS",                         "sensor",     1),
    ("Motor Driver",                "board",      1),
    ("Phillips Screwdriver",        "tool",       1),
    ("Screw Gauge 3D",              "tool",       1),
    ("Standoff Tool 3D",            "tool",       1),
    ("CDHS Board",                  "board",      1),
    ("EPS Board",                   "board",      1),
    ("ADCS Board",                  "board",      1),
    ("ESP32-CAM",                   "board",      1),
    ("ESP32",                       "board",      1),
    ("Magnetorquer",                "other",      1),
    ("Buck Converter Module",       "board",      1),
    ("Li-ion Battery",              "other",      1),
    ("Pin Socket",                  "mechanical", 4),
    ("M3 Screw",                    "mechanical", 20),
    ("M3 Hex Nut",                  "mechanical", 4),
    ("M3 9.6mm Brass Standoff",     "mechanical", 4),
    ("M3 10mm Brass Standoff",      "mechanical", 4),
    ("M3 10.6mm Brass Standoff",    "mechanical", 12),
    ("M3 20.6mm Brass Standoff",    "mechanical", 8),
]

# Merchandise. Tracked by type AND size per the CEO. Vests and jackets default
# to returnable; T-shirts do not — a policy of "return your T-shirt" that
# nobody follows would fill the overdue list with noise and stop it working
# for kits, which is what it is actually for.
# (display name, category, returnable_default)
MERCH = [
    (f"{kind} ({size})", "merch", kind != "T-Shirt")
    for kind in ("T-Shirt", "Vest", "Jacket")
    for size in ("XS", "S", "M", "L", "XL")
]

# Non-kit equipment an instructor picks up on the way to a workshop (I2-7).
# These are the CEO's own examples — the things currently photographed into
# WhatsApp. Seeding the *names* means ops enters counts instead of typing a
# catalogue; the counts themselves are nobody's to guess and are left to I1-5.
#
# Category is `other`: nothing branches on it, it only groups the catalogue.
# (display name, category, returnable_default)
EQUIPMENT = [
    ("Mic Speaker",         "other", True),
    ("Battery Charger",     "other", True),
    ("Extension Cable",     "other", True),
    ("Projector",           "other", True),
    ("Laptop (spare)",      "other", True),
    ("Sticker Roll",        "other", False),
    ("Banner / Roll-up",    "other", True),
    ("First Aid Kit",       "other", True),
]


async def seed(db: AsyncSession, *, dry_run: bool) -> None:
    created = {"locations": 0, "items": 0, "templates": 0, "bom_lines": 0}
    skipped = {"locations": 0, "items": 0, "templates": 0, "bom_lines": 0}
    conflicts: list[str] = []

    # locations
    for name, country in LOCATIONS:
        existing = (await db.execute(select(Location).where(Location.name == name))).scalars().first()
        if existing:
            skipped["locations"] += 1
            continue
        db.add(Location(id=uuid.uuid4(), name=name, country=country))
        created["locations"] += 1
    await db.flush()

    # items — kit components, then merch, then non-kit equipment.
    wanted_items = (
        [(n, c, False) for n, c, _q in SATKIT_BOM]
        + list(MERCH)
        + list(EQUIPMENT)
    )
    items_by_name: dict[str, Item] = {}
    for name, category, returnable in wanted_items:
        existing = (await db.execute(select(Item).where(Item.name == name))).scalars().first()
        if existing:
            items_by_name[name] = existing
            skipped["items"] += 1
            continue
        item = Item(
            id=uuid.uuid4(), name=name, category=category,
            returnable_default=returnable,
        )
        db.add(item)
        items_by_name[name] = item
        created["items"] += 1
    await db.flush()

    # the SatKit template
    template = (await db.execute(select(KitTemplate).where(KitTemplate.code == "SATKIT"))).scalars().first()
    if template is None:
        template = KitTemplate(id=uuid.uuid4(), name="SatKit v1", code="SATKIT")
        db.add(template)
        created["templates"] += 1
        await db.flush()
    else:
        skipped["templates"] += 1

    # MPKIT is confirmed to exist as a second type, but nobody has given us its
    # contents — an empty template is honest; a guessed one is not.
    if (await db.execute(select(KitTemplate).where(KitTemplate.code == "MPKIT"))).scalars().first() is None:
        db.add(KitTemplate(id=uuid.uuid4(), name="Mission Payload Kit", code="MPKIT"))
        created["templates"] += 1
    else:
        skipped["templates"] += 1
    await db.flush()

    # bill of materials
    for name, _category, qty in SATKIT_BOM:
        item = items_by_name[name]
        line = (await db.execute(select(KitTemplateItem).where(
            KitTemplateItem.template_id == template.id, KitTemplateItem.item_id == item.id
        ))).scalars().first()
        if line is not None:
            skipped["bom_lines"] += 1
            if line.required_qty != qty:
                conflicts.append(f"  {name}: database says {line.required_qty}, this script says {qty} — left alone")
            continue
        db.add(KitTemplateItem(
            id=uuid.uuid4(), template_id=template.id, item_id=item.id, required_qty=qty
        ))
        created["bom_lines"] += 1

    await db.flush()

    for label in created:
        print(f"{label:12} created {created[label]:3}   already present {skipped[label]:3}")
    if conflicts:
        print("\nQuantities that disagree (database kept, nothing changed):")
        print("\n".join(conflicts))

    if dry_run:
        print("\n--dry-run: rolling back, nothing written.")
    else:
        await db.commit()
        print("\nCommitted. Now verify the SatKit quantities against a real box — "
              "they came from the legacy app, not from anyone counting recently.")


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
