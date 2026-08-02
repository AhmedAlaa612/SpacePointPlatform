"""The seed script must be safe to run twice (I1-5).

The R2-6 precedent: `backfill_user_contacts` had a real bug — a missing flush
meant a second run created duplicates — and only the mandatory
re-run-is-idempotent test caught it. Same rule applies here, and the stakes
are higher: this script runs against the database that will hold the real
fleet.
"""

import pytest
from sqlalchemy import func, select

from app.models.inventory import Item, KitTemplate, KitTemplateItem, Location
from scripts.seed_inventory import SATKIT_BOM, seed


async def _counts(db) -> dict[str, int]:
    return {
        "locations": await db.scalar(select(func.count()).select_from(Location)),
        "items": await db.scalar(select(func.count()).select_from(Item)),
        "templates": await db.scalar(select(func.count()).select_from(KitTemplate)),
        "bom": await db.scalar(select(func.count()).select_from(KitTemplateItem)),
    }


@pytest.mark.asyncio
async def test_seeding_twice_creates_nothing_the_second_time(db):
    await seed(db, dry_run=True)
    after_first = await _counts(db)
    assert after_first["locations"] == 5
    assert after_first["templates"] == 2, "SATKIT and MPKIT"
    assert after_first["bom"] == len(SATKIT_BOM)

    await seed(db, dry_run=True)
    assert await _counts(db) == after_first


@pytest.mark.asyncio
async def test_the_satkit_bom_is_seeded_against_the_right_template(db):
    await seed(db, dry_run=True)

    satkit = (await db.execute(select(KitTemplate).where(KitTemplate.code == "SATKIT"))).scalars().first()
    mpkit = (await db.execute(select(KitTemplate).where(KitTemplate.code == "MPKIT"))).scalars().first()

    satkit_lines = await db.scalar(
        select(func.count()).select_from(KitTemplateItem).where(KitTemplateItem.template_id == satkit.id)
    )
    mpkit_lines = await db.scalar(
        select(func.count()).select_from(KitTemplateItem).where(KitTemplateItem.template_id == mpkit.id)
    )
    assert satkit_lines == len(SATKIT_BOM)
    assert mpkit_lines == 0, "nobody has told us what an MPKIT contains — an empty template is honest"


@pytest.mark.asyncio
async def test_an_existing_quantity_is_never_overwritten(db):
    """Somebody counting a real box beats a number transcribed from the legacy
    app. If they disagree, the database wins."""
    await seed(db, dry_run=True)

    satkit = (await db.execute(select(KitTemplate).where(KitTemplate.code == "SATKIT"))).scalars().first()
    screw = (await db.execute(select(Item).where(Item.name == "M3 Screw"))).scalars().first()
    line = (await db.execute(select(KitTemplateItem).where(
        KitTemplateItem.template_id == satkit.id, KitTemplateItem.item_id == screw.id
    ))).scalars().first()

    line.required_qty = 16  # someone counted
    await db.flush()

    await seed(db, dry_run=True)
    await db.refresh(line)
    assert line.required_qty == 16


@pytest.mark.asyncio
async def test_merch_is_sized_and_only_the_right_things_come_back(db):
    await seed(db, dry_run=True)

    merch = (await db.execute(select(Item).where(Item.category == "merch"))).scalars().all()
    names = {m.name for m in merch}
    assert "Vest (L)" in names and "T-Shirt (M)" in names and "Jacket (XL)" in names

    by_name = {m.name: m for m in merch}
    assert by_name["Vest (L)"].returnable_default is True
    assert by_name["Jacket (XL)"].returnable_default is True
    assert by_name["T-Shirt (M)"].returnable_default is False, (
        "a return policy nobody follows fills the overdue list with noise "
        "and stops it working for kits"
    )
