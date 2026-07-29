"""Stock levels, stock movements and the movement ledger (I1-3).

Reads are `require_operations`. The three *writes* here — moving stock,
adjusting a count, confirming a movement — are `require_storekeeper`, which
admits `storekeeper` **or** `operations`. That is the whole shape of the
storekeeper role: they can do these and nothing else, because every other
inventory endpoint is `require_operations` and that guard does not list them.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations, require_storekeeper
from app.db.session import get_db
from app.models.inventory.item import Item
from app.models.inventory.location import Location
from app.models.inventory.movement import Movement
from app.models.inventory.stock import StockLevel
from app.models.user import User
from app.schemas.inventory.kits import (
    MovementOut,
    StockAdjustIn,
    StockLevelOut,
    StockMoveIn,
)
from app.services.inventory import adjust_stock, confirm, move, overdue

router = APIRouter(prefix="/inventory", tags=["inventory-stock"])


@router.get("/stock", response_model=list[StockLevelOut])
async def list_stock(
    location_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    stmt = (
        select(StockLevel, Item, Location)
        .join(Item, Item.id == StockLevel.item_id)
        .join(Location, Location.id == StockLevel.location_id)
        .order_by(Location.name, Item.name)
    )
    if location_id:
        stmt = stmt.where(StockLevel.location_id == location_id)
    if item_id:
        stmt = stmt.where(StockLevel.item_id == item_id)

    return [
        StockLevelOut(
            item_id=item.id, item_name=item.name,
            location_id=location.id, location_name=location.name,
            qty=level.qty,
        )
        for level, item, location in (await db.execute(stmt)).all()
    ]


@router.post("/stock/move", response_model=MovementOut, status_code=status.HTTP_201_CREATED)
async def move_stock(
    body: StockMoveIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_storekeeper),
):
    """Move a quantity of one item. A refill into a kit is
    `from_location_id` + `to_kit_id`; receiving goods has no source."""
    movement = await move(
        db,
        actor_user_id=current_user.id,
        reason=body.reason,
        item_id=body.item_id,
        qty=body.qty,
        from_location_id=body.from_location_id,
        from_kit_id=body.from_kit_id,
        to_location_id=body.to_location_id,
        to_user_id=body.to_user_id,
        to_kit_id=body.to_kit_id,
        due_back_on=body.due_back_on,
        note=body.note,
    )
    await db.commit()
    await db.refresh(movement)
    return movement


@router.post("/stock/adjust", response_model=MovementOut, status_code=status.HTTP_201_CREATED)
async def adjust(
    body: StockAdjustIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_storekeeper),
):
    """Correct a stock level to the counted total. Reason is mandatory."""
    if await db.get(Item, body.item_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown item")
    if await db.get(Location, body.location_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown location")

    movement = await adjust_stock(
        db,
        actor_user_id=current_user.id,
        item_id=body.item_id,
        location_id=body.location_id,
        new_qty=body.new_qty,
        reason=body.reason,
    )
    await db.commit()
    await db.refresh(movement)
    return movement


# ── the ledger ──────────────────────────────────────────────────────────────

@router.get("/movements", response_model=list[MovementOut])
async def list_movements(
    kit_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    unconfirmed_only: bool = False,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    stmt = select(Movement).order_by(Movement.created_at.desc()).limit(min(limit, 500))
    if kit_id:
        stmt = stmt.where(Movement.kit_id == kit_id)
    if item_id:
        stmt = stmt.where(Movement.item_id == item_id)
    if session_id:
        stmt = stmt.where(Movement.session_id == session_id)
    if unconfirmed_only:
        # The gap that matters: marked out, never acknowledged.
        stmt = stmt.where(Movement.confirmed_at.is_(None))
    return (await db.execute(stmt)).scalars().all()


@router.post("/movements/{movement_id}/confirm", response_model=MovementOut)
async def confirm_movement(
    movement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_storekeeper),
):
    """The other party agrees this happened. Idempotent — the first
    confirmation stands, because that is when agreement actually occurred."""
    movement = await db.get(Movement, movement_id)
    if movement is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Movement not found")
    await confirm(db, movement, actor_user_id=current_user.id)
    await db.commit()
    await db.refresh(movement)
    return movement


@router.get("/overdue", response_model=list[MovementOut])
async def list_overdue(
    as_of: date | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """Issued to a person, past its due date, not yet returned. Nothing
    without a deadline ever appears — otherwise the list becomes noise and
    stops being read."""
    return await overdue(db, as_of=as_of)
