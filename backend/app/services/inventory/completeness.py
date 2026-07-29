"""Is this kit complete, and if not what is short?

Computed, never stored. The legacy system kept an `iscomplete` boolean and a
`missingitems` text blob on the kit row, both of which went stale the moment
anyone edited a count — and did, visibly, in production.

Consumables are excluded entirely. There are 20 M3 screws in a SatKit; a
post-workshop count is always "short a few", so including them means the
shortage list always has entries and nobody reads it — including the line
about the missing ADCS board. They surface as a restock suggestion instead
(I4-1), not as a kit being incomplete.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.item import Item
from app.models.inventory.kit import Kit, KitItem
from app.models.inventory.kit_template import KitTemplateItem


async def kit_shortages(db: AsyncSession, kit: Kit) -> list[dict]:
    """Every non-consumable item this kit is short of, worst gap first.

    An item on the template with no `kit_items` row at all counts as zero
    present — a missing row and a row saying 0 mean the same thing physically,
    and treating them differently is how "the kit looks complete because we
    never recorded that component" happens.
    """
    rows = (await db.execute(
        select(KitTemplateItem, Item, KitItem)
        .join(Item, Item.id == KitTemplateItem.item_id)
        .outerjoin(
            KitItem,
            (KitItem.item_id == KitTemplateItem.item_id) & (KitItem.kit_id == kit.id),
        )
        .where(
            KitTemplateItem.template_id == kit.template_id,
            Item.is_consumable.is_(False),
        )
    )).all()

    shortages = []
    for template_item, item, kit_item in rows:
        actual = kit_item.qty if kit_item is not None else 0
        if actual < template_item.required_qty:
            shortages.append({
                "item_id": item.id,
                "item_name": item.name,
                "required": template_item.required_qty,
                "actual": actual,
                "short_by": template_item.required_qty - actual,
            })

    shortages.sort(key=lambda s: (-s["short_by"], s["item_name"]))
    return shortages


async def is_complete(db: AsyncSession, kit: Kit) -> bool:
    return not await kit_shortages(db, kit)


async def shortages_for_kits(db: AsyncSession, kit_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """How many distinct items each kit is short — for list views, which need
    a completeness badge per row and must not run one query per kit."""
    if not kit_ids:
        return {}

    kits = (await db.execute(select(Kit).where(Kit.id.in_(kit_ids)))).scalars().all()
    template_ids = {k.template_id for k in kits}

    required = (await db.execute(
        select(KitTemplateItem.template_id, KitTemplateItem.item_id, KitTemplateItem.required_qty)
        .join(Item, Item.id == KitTemplateItem.item_id)
        .where(KitTemplateItem.template_id.in_(template_ids), Item.is_consumable.is_(False))
    )).all()

    held = (await db.execute(
        select(KitItem.kit_id, KitItem.item_id, KitItem.qty).where(KitItem.kit_id.in_(kit_ids))
    )).all()
    held_by = {(kit_id, item_id): qty for kit_id, item_id, qty in held}

    by_template: dict[uuid.UUID, list[tuple[uuid.UUID, int]]] = {}
    for template_id, item_id, required_qty in required:
        by_template.setdefault(template_id, []).append((item_id, required_qty))

    return {
        kit.id: sum(
            1
            for item_id, required_qty in by_template.get(kit.template_id, [])
            if held_by.get((kit.id, item_id), 0) < required_qty
        )
        for kit in kits
    }
