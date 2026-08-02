"""Self-serve holdings — what one person currently has, and giving it back
themselves (2026-08-01).

Kits already have their own hold (`current_holder_user_id`) and their own
listing (`/inventory/my-kits`); this adds the return action for them, plus
both the listing and the return action for bulk items — equipment or merch,
the ledger doesn't distinguish and neither does this.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_session_delivery
from app.db.session import get_db
from app.models.inventory.warehouse import Warehouse
from app.models.user import User
from app.schemas.inventory.holdings import MyHeldItemOut, ReturnOwnItemIn, ReturnOwnKitIn
from app.schemas.inventory.kits import MovementOut
from app.services.inventory import my_held_items, return_own_item, return_own_kit

router = APIRouter(prefix="/inventory", tags=["inventory-holdings"])


@router.get("/my-holdings/items", response_model=list[MyHeldItemOut])
async def my_holding_items(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Equipment and merch this person currently has, wherever it came from —
    a session pickup, or something ops handed them directly."""
    lines = await my_held_items(db, current_user.id)
    warehouse_ids = {l["default_warehouse_id"] for l in lines if l["default_warehouse_id"]}
    names = dict((await db.execute(
        select(Warehouse.id, Warehouse.name).where(Warehouse.id.in_(warehouse_ids))
    )).all()) if warehouse_ids else {}
    return [
        MyHeldItemOut(**line, default_warehouse_name=names.get(line["default_warehouse_id"]))
        for line in lines
    ]


@router.post(
    "/my-holdings/kits/{kit_id}/return", response_model=MovementOut, status_code=status.HTTP_201_CREATED,
)
async def return_my_kit(
    kit_id: uuid.UUID,
    body: ReturnOwnKitIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Bring back a kit you're holding, on your own — no ops button needed."""
    movement = await return_own_kit(
        db, actor_user_id=current_user.id, kit_id=kit_id, to_warehouse_id=body.to_warehouse_id, note=body.note,
    )
    await db.commit()
    await db.refresh(movement)
    return movement


@router.post(
    "/my-holdings/items/{item_id}/return", response_model=MovementOut, status_code=status.HTTP_201_CREATED,
)
async def return_my_item(
    item_id: uuid.UUID,
    body: ReturnOwnItemIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    movement = await return_own_item(
        db, actor_user_id=current_user.id, item_id=item_id, qty=body.qty,
        to_warehouse_id=body.to_warehouse_id, note=body.note,
    )
    await db.commit()
    await db.refresh(movement)
    return movement
