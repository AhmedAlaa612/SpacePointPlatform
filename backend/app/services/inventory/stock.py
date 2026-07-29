"""Manual stock corrections.

An adjustment is a `Movement` row like everything else — there is no separate
adjustments table. The legacy system had `component_logs` alongside
`components`; keeping one ledger means "why is there one fewer of these than
last week" has a single place to look.

NOTE: refilling a kit from warehouse stock is deliberately NOT here. It
belongs to the storekeeper fulfilment loop (I3-1), and it needs a schema
decision first — see INVENTORY_EXECUTION_PLAN.md §DISCOVERIES (I1-2): a
movement's destination can currently be a location or a person, but not a
kit, so "5 MPUs went into SP-SATKIT-0012" has nowhere to live.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.movement import Movement
from app.models.inventory.stock import StockLevel


async def adjust_stock(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    item_id: uuid.UUID,
    location_id: uuid.UUID,
    new_qty: int,
    reason: str,
) -> Movement:
    """Set a stock level to a counted figure — a stocktake correction.

    Takes the *counted total*, not a delta, because that is what the person
    holding the clipboard actually knows. The delta is derived and recorded.

    A reason is mandatory. An unexplained inventory change is precisely the
    thing you want an explanation for six weeks later.
    """
    if new_qty < 0:
        raise HTTPException(400, detail="Stock cannot be negative")
    if not reason or not reason.strip():
        raise HTTPException(400, detail="An adjustment needs a reason")

    level = (await db.execute(
        select(StockLevel).where(
            StockLevel.item_id == item_id, StockLevel.location_id == location_id
        )
    )).scalars().first()

    current = level.qty if level is not None else 0
    delta = new_qty - current
    if delta == 0:
        raise HTTPException(409, detail="That is already the recorded quantity")

    if level is None:
        level = StockLevel(id=uuid.uuid4(), item_id=item_id, location_id=location_id, qty=0)
        db.add(level)
    level.qty = new_qty

    # No from/to: nothing moved anywhere, the count was simply wrong. `qty`
    # carries the magnitude (the column is constrained positive) and the note
    # carries the direction and the before/after.
    movement = Movement(
        id=uuid.uuid4(),
        item_id=item_id,
        qty=abs(delta),
        reason="adjust",
        note=f"{'+' if delta > 0 else '-'}{abs(delta)} ({current} → {new_qty}): {reason.strip()}",
        created_by=actor_user_id,
    )
    db.add(movement)
    await db.flush()
    return movement
