"""Merchandise handovers (I2-4).

Vests, jackets, T-shirts — bulk items given to a person and, for the
returnable ones, expected back. Kits have no equivalent leg: they're assigned
to a session and the instructor reports on them directly (see
`services/inventory/session_kits.py`), with no separate issue/collect step.
"""

import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.item import Item
from app.models.inventory.movement import Movement
from app.services.inventory.movements import move


# ── merchandise ─────────────────────────────────────────────────────────────

async def issue_merch(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    item_id: uuid.UUID,
    to_user_id: uuid.UUID,
    from_warehouse_id: uuid.UUID,
    qty: int = 1,
    returnable: bool | None = None,
    due_back_on: date | None = None,
    note: str | None = None,
) -> Movement:
    """Give someone a vest, a jacket or a T-shirt.

    `returnable` defaults to the item's own setting so ops isn't answering the
    same question fifty times, but stays overridable per issue. A due date is
    only meaningful on something expected back — putting one on a T-shirt
    nobody will return fills the overdue list with noise and stops it working
    for kits, which is what it is actually for.
    """
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(404, detail="Item not found")

    if returnable is None:
        returnable = item.returnable_default
    if not returnable:
        due_back_on = None

    return await move(
        db,
        actor_user_id=actor_user_id,
        reason="issue",
        item_id=item_id,
        qty=qty,
        from_warehouse_id=from_warehouse_id,
        to_user_id=to_user_id,
        due_back_on=due_back_on,
        note=note,
    )


async def held_by_user(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """What bulk items this person currently holds.

    Derived from the ledger rather than a denormalised column: issue and
    return quantities net out. Kits keep a denormalised holder because kit
    lists read it constantly; bulk holdings are rare enough to compute, and
    one fewer thing to keep honest.
    """
    out = (await db.execute(
        select(Movement, Item)
        .join(Item, Item.id == Movement.item_id)
        .where(Movement.to_user_id == user_id, Movement.item_id.isnot(None))
    )).all()
    back = (await db.execute(
        select(Movement).where(Movement.from_user_id == user_id, Movement.item_id.isnot(None))
    )).scalars().all()

    net: dict[uuid.UUID, dict] = {}
    for movement, item in out:
        entry = net.setdefault(item.id, {
            "item_id": item.id, "item_name": item.name,
            "variant_group": item.variant_group, "variant_label": item.variant_label,
            "qty": 0, "due_back_on": None,
        })
        entry["qty"] += movement.qty or 0
        if movement.due_back_on and (
            entry["due_back_on"] is None or movement.due_back_on < entry["due_back_on"]
        ):
            entry["due_back_on"] = movement.due_back_on

    for movement in back:
        entry = net.get(movement.item_id)
        if entry:
            entry["qty"] -= movement.qty or 0

    return [e for e in net.values() if e["qty"] > 0]


async def return_merch(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    item_id: uuid.UUID,
    from_user_id: uuid.UUID,
    to_warehouse_id: uuid.UUID,
    qty: int = 1,
    note: str | None = None,
) -> Movement:
    held = {h["item_id"]: h["qty"] for h in await held_by_user(db, from_user_id)}
    if held.get(item_id, 0) < qty:
        raise HTTPException(
            409, detail=f"They only have {held.get(item_id, 0)} of those to give back"
        )

    return await move(
        db,
        actor_user_id=actor_user_id,
        reason="return",
        item_id=item_id,
        qty=qty,
        from_user_id=from_user_id,
        to_warehouse_id=to_warehouse_id,
        note=note,
    )
