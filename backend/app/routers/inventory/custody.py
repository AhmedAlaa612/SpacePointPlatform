"""Merchandise endpoints (I2-4).

Kits have no equivalent here — they're assigned to a session and the
instructor reports on them directly (see routers/inventory/checks.py), with
no separate issue/collect/return-to-a-location step.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations, require_session_delivery
from app.db.session import get_db
from app.models.user import User
from app.schemas.inventory.custody import HeldItemOut, IssueMerchIn, ReturnMerchIn
from app.schemas.inventory.kits import MovementOut
from app.services.inventory import held_by_user, issue_merch, return_merch

router = APIRouter(prefix="/inventory", tags=["inventory-custody"])


# ── merchandise ─────────────────────────────────────────────────────────────

@router.post("/merch/issue", response_model=MovementOut, status_code=status.HTTP_201_CREATED)
async def give_merch(
    body: IssueMerchIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Whether it comes back defaults to the item's own setting — vests yes,
    T-shirts no — and stays overridable per issue."""
    movement = await issue_merch(
        db,
        actor_user_id=current_user.id,
        item_id=body.item_id,
        to_user_id=body.to_user_id,
        from_warehouse_id=body.from_warehouse_id,
        qty=body.qty,
        returnable=body.returnable,
        due_back_on=body.due_back_on,
        note=body.note,
    )
    await db.commit()
    await db.refresh(movement)
    return movement


@router.post("/merch/return", response_model=MovementOut, status_code=status.HTTP_201_CREATED)
async def take_merch_back(
    body: ReturnMerchIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    movement = await return_merch(
        db,
        actor_user_id=current_user.id,
        item_id=body.item_id,
        from_user_id=body.from_user_id,
        to_warehouse_id=body.to_warehouse_id,
        qty=body.qty,
    )
    await db.commit()
    await db.refresh(movement)
    return movement


@router.get("/merch/held/{user_id}", response_model=list[HeldItemOut])
async def merch_held_by(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    return [HeldItemOut(**h) for h in await held_by_user(db, user_id)]


@router.get("/my-merch", response_model=list[HeldItemOut])
async def my_merch(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """What I'm holding, and what I owe back."""
    return [HeldItemOut(**h) for h in await held_by_user(db, current_user.id)]
