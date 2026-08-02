"""Manual stock corrections.

An adjustment is a `Movement` row like everything else — there is no separate
adjustments table. The legacy system had `component_logs` alongside
`components`; keeping one ledger means "why is there one fewer of these than
last week" has a single place to look.

Refilling a kit is `move(item_id=…, from_warehouse_id=…, to_kit_id=…)` — the
schema gap that blocked it is closed (migration e6b2d84a0017). The storekeeper
*workflow* around it (a shortage becoming a task, and closing that task) is
still I3-1; the mechanic itself lives in `move()`, so there is one write path
rather than two.
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
    warehouse_id: uuid.UUID,
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
            StockLevel.item_id == item_id, StockLevel.warehouse_id == warehouse_id
        )
    )).scalars().first()

    current = level.qty if level is not None else 0
    delta = new_qty - current
    if delta == 0:
        raise HTTPException(409, detail="That is already the recorded quantity")

    if level is None:
        level = StockLevel(id=uuid.uuid4(), item_id=item_id, warehouse_id=warehouse_id, qty=0)
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
