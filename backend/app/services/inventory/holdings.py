"""Everything one person is currently holding, and giving it back themselves.

No new state: a kit's holder and an item's outstanding ledger balance are
already the source of truth (`Kit.current_holder_user_id`, `held_by_user`).
This is the self-serve side of that — whoever has something can hand it back
without ops needing to be in the room, the same way an instructor already
returns same-session equipment on their own.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.equipment_flag import EquipmentReturnFlag
from app.models.inventory.kit import Kit
from app.models.inventory.movement import Movement
from app.services.inventory.custody import held_by_user, return_merch
from app.services.inventory.equipment import pickup_warehouse
from app.services.inventory.movements import move


async def _last_issue(db: AsyncSession, *, item_id=None, kit_id=None, user_id: uuid.UUID) -> Movement | None:
    stmt = select(Movement).where(
        Movement.to_user_id == user_id, Movement.reason == "issue",
    ).order_by(Movement.created_at.desc()).limit(1)
    stmt = stmt.where(Movement.item_id == item_id) if item_id else stmt.where(Movement.kit_id == kit_id)
    return (await db.execute(stmt)).scalars().first()


async def default_kit_return_warehouse(db: AsyncSession, kit: Kit) -> uuid.UUID:
    """Where a held kit goes back to if nobody says otherwise: the session it
    was last issued for, if there was one — that warehouse is why it left in
    the first place. Falls back to wherever the kit is already recorded as
    living, which is never wrong, just possibly not where it physically is."""
    last_issue = await _last_issue(db, kit_id=kit.id, user_id=kit.current_holder_user_id)
    if last_issue and last_issue.session_id:
        warehouse = await pickup_warehouse(db, last_issue.session_id)
        if warehouse:
            return warehouse.id
    return kit.current_warehouse_id


async def default_item_return_warehouse(
    db: AsyncSession, *, item_id: uuid.UUID, user_id: uuid.UUID
) -> uuid.UUID | None:
    """Same idea for a held item — the session it was picked up for if there
    was one, else wherever it was picked up from. `None` only when neither
    can be resolved, which is the one time the caller has to ask."""
    last_issue = await _last_issue(db, item_id=item_id, user_id=user_id)
    if last_issue is None:
        return None
    if last_issue.session_id:
        warehouse = await pickup_warehouse(db, last_issue.session_id)
        if warehouse:
            return warehouse.id
    return last_issue.from_warehouse_id


async def my_held_items(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """`held_by_user`, plus where each line would default to going back."""
    held = await held_by_user(db, user_id)
    for line in held:
        line["default_warehouse_id"] = await default_item_return_warehouse(
            db, item_id=line["item_id"], user_id=user_id,
        )
    return held


async def return_own_kit(
    db: AsyncSession, *, actor_user_id: uuid.UUID, kit_id: uuid.UUID, to_warehouse_id: uuid.UUID | None = None, note: str | None = None,
) -> Movement:
    """The holder brings their own kit back. 404, not 403, on someone else's
    kit — matches this codebase's don't-leak-existence convention."""
    kit = await db.get(Kit, kit_id)
    if kit is None or kit.current_holder_user_id != actor_user_id:
        raise HTTPException(404, detail="You aren't holding that kit")
    if to_warehouse_id is None:
        to_warehouse_id = await default_kit_return_warehouse(db, kit)
    return await move(
        db, actor_user_id=actor_user_id, reason="return", kit_id=kit.id,
        from_user_id=actor_user_id, to_warehouse_id=to_warehouse_id, note=note,
    )


async def return_own_item(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    item_id: uuid.UUID,
    qty: int,
    to_warehouse_id: uuid.UUID | None = None,
    note: str | None = None,
) -> Movement:
    """The holder brings their own item back — whether it came from a
    session pickup or a direct ops issue, the ledger doesn't distinguish and
    neither does this. Clears any "return later" flag left over from the
    session equipment panel, regardless of which session it was set under,
    since the item is now actually back."""
    if to_warehouse_id is None:
        to_warehouse_id = await default_item_return_warehouse(db, item_id=item_id, user_id=actor_user_id)
        if to_warehouse_id is None:
            raise HTTPException(409, detail="Say where this is going back to")

    movement = await return_merch(
        db, actor_user_id=actor_user_id, item_id=item_id, from_user_id=actor_user_id,
        to_warehouse_id=to_warehouse_id, qty=qty, note=note,
    )
    await db.execute(
        delete(EquipmentReturnFlag).where(
            EquipmentReturnFlag.item_id == item_id, EquipmentReturnFlag.user_id == actor_user_id,
        )
    )
    return movement
