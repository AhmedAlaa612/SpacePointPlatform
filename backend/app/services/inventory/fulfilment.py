"""The storekeeper's queue: kits that are short, and putting parts back in
them (I3-1).

This is the other half of the loop the post-session check opens. An
instructor counts a kit, finds four MPUs where there should be five, and that
shortage has to reach somebody who can act on it. Until now it was visible
on the kit's own page and nowhere else, which means it was visible to nobody
— the storekeeper does not browse kits one at a time.

**There is no task table, and that is deliberate.** The task *is* the
shortage: it is computed from the template against the kit's contents, and
refilling the kit makes it disappear without anything being closed. The one
fact that cannot be derived is the storekeeper's judgment that the shelf was
empty — recorded as `kits.awaiting_parts_since`. See the migration
(`b1f6a38d0020`) for the full reasoning and the legacy table that argues it.

**Fulfilling is an ordinary `refill` movement into the kit** — the
`to_kit_id` side added in `e6b2d84a0017` exists exactly for this. Stock
leaves the shelf and arrives in the box in one transaction, so the ledger and
both balances cannot disagree.

Reads and writes here are `require_storekeeper`, which admits `storekeeper`
**or** `operations`. This is the third thing that role can do, and the whole
of what it is for.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.item import Item
from app.models.inventory.kit import Kit
from app.models.inventory.kit_template import KitTemplate
from app.models.inventory.location import Location
from app.models.inventory.stock import StockLevel
from app.models.inventory.movement import Movement
from app.services.inventory.completeness import kit_shortages
from app.services.inventory.movements import move


async def fulfilment_queue(db: AsyncSession, *, location_id: uuid.UUID | None = None) -> list[dict]:
    """Every kit that is short something, with what it would take to fix it.

    Each shortage line carries `available` — how many are on the shelf **at
    that kit's own location**. Without it the storekeeper reads the list, walks
    to the shelf, and only then finds out; with it, the list already says
    which lines can be closed today and which cannot.

    Retired and lost kits are excluded. Chasing parts for a box that is gone
    is noise, and noise is what stops a list being read.
    """
    kits = (await db.execute(
        select(Kit)
        .where(Kit.status.notin_(["retired", "lost"]))
        .order_by(Kit.label)
    )).scalars().all()
    if location_id is not None:
        kits = [k for k in kits if k.current_location_id == location_id]
    if not kits:
        return []

    templates = dict((await db.execute(
        select(KitTemplate.id, KitTemplate.name)
        .where(KitTemplate.id.in_({k.template_id for k in kits}))
    )).all())
    locations = dict((await db.execute(
        select(Location.id, Location.name)
        .where(Location.id.in_({k.current_location_id for k in kits}))
    )).all())

    # One stock query for the whole queue rather than one per kit — the
    # storekeeper's list is the page most likely to grow.
    levels = {
        (item_id, loc_id): qty
        for item_id, loc_id, qty in (await db.execute(
            select(StockLevel.item_id, StockLevel.location_id, StockLevel.qty)
            .where(StockLevel.location_id.in_({k.current_location_id for k in kits}))
        )).all()
    }

    queue = []
    for kit in kits:
        shortages = await kit_shortages(db, kit)
        if not shortages:
            continue
        lines = [
            {
                **shortage,
                "available": levels.get((shortage["item_id"], kit.current_location_id), 0),
            }
            for shortage in shortages
        ]
        queue.append({
            "kit_id": kit.id,
            "label": kit.label,
            "template_name": templates.get(kit.template_id, ""),
            "status": kit.status,
            "location_id": kit.current_location_id,
            "location_name": locations.get(kit.current_location_id, ""),
            "out_with_someone": kit.current_holder_user_id is not None,
            "awaiting_parts_since": kit.awaiting_parts_since,
            "awaiting_parts_note": kit.awaiting_parts_note,
            "shortages": lines,
            # What the storekeeper can actually close today.
            "fixable_now": sum(1 for l in lines if l["available"] >= l["short_by"]),
        })
    return queue


async def fulfil_kit(
    db: AsyncSession,
    *,
    kit: Kit,
    lines: list[tuple[uuid.UUID, int]],
    actor_user_id: uuid.UUID,
    from_location_id: uuid.UUID | None = None,
) -> list[Movement]:
    """Put parts into the kit from a warehouse shelf.

    Defaults to the kit's own location — parts come off the shelf the box is
    sitting on, which is the case that needs no thinking about. `move()`
    refuses to drive stock negative, so a line the shelf cannot cover fails
    rather than inventing quantity.

    Clears `awaiting_parts` when the kit ends up complete: the flag means
    "still waiting", and a kit that isn't short of anything isn't.
    """
    if not lines:
        raise HTTPException(400, detail="Nothing to fulfil")

    if from_location_id is None:
        from_location_id = kit.current_location_id
    elif await db.get(Location, from_location_id) is None:
        raise HTTPException(404, detail="Location not found")

    movements = []
    for item_id, qty in lines:
        if qty <= 0:
            raise HTTPException(400, detail="A quantity has to be positive")
        if await db.get(Item, item_id) is None:
            raise HTTPException(404, detail="Item not found")
        movements.append(await move(
            db,
            actor_user_id=actor_user_id,
            reason="refill",
            item_id=item_id,
            qty=qty,
            from_location_id=from_location_id,
            to_kit_id=kit.id,
            note="Fulfilling a shortage",
        ))

    if not await kit_shortages(db, kit):
        kit.awaiting_parts_since = None
        kit.awaiting_parts_note = None

    await db.flush()
    return movements


async def set_awaiting_parts(
    db: AsyncSession, *, kit: Kit, awaiting: bool, note: str | None = None
) -> Kit:
    """Flag (or clear) "I looked and the shelf was empty".

    Refusing to flag a kit that isn't short of anything is deliberate: the
    flag's whole meaning is "still waiting for something", and letting it sit
    on a complete kit is how a list stops being trustworthy.

    Setting it twice keeps the original timestamp. How long a kit has been
    waiting is the number worth having, and re-flagging it would reset the
    clock on exactly the kits that have waited longest.
    """
    if awaiting:
        if not await kit_shortages(db, kit):
            raise HTTPException(409, detail="This kit isn't short of anything")
        if kit.awaiting_parts_since is None:
            kit.awaiting_parts_since = datetime.now(timezone.utc)
        kit.awaiting_parts_note = (note or "").strip() or None
    else:
        kit.awaiting_parts_since = None
        kit.awaiting_parts_note = None

    await db.flush()
    return kit
