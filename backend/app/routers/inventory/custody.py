"""Merchandise endpoints (I2-4).

Kits have no equivalent here — they're assigned to a session and the
instructor reports on them directly (see routers/inventory/checks.py), with
no separate issue/collect/return-to-a-location step.

Issuing/returning merch is `require_inventory_manage` (operations or coo) —
handing a T-shirt or vest to a person is ops logistics, not the storekeeper's
restock job. `GET /merch/held/{user_id}` is `require_storekeeper` (read
everything, 2026-08-27).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_inventory_manage, require_session_delivery, require_storekeeper
from app.db.session import get_db
from app.models.inventory.item import Item
from app.models.user import User
from app.schemas.inventory.custody import HeldItemOut, IssueMerchIn, ReturnMerchIn
from app.schemas.inventory.kits import MovementOut
from app.services.inventory import gate, held_by_user, issue_merch, return_merch

router = APIRouter(prefix="/inventory", tags=["inventory-custody"])


# ── merchandise ─────────────────────────────────────────────────────────────

@router.post("/merch/issue", response_model=MovementOut, status_code=status.HTTP_201_CREATED)
async def give_merch(
    body: IssueMerchIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_inventory_manage),
):
    """Whether it comes back defaults to the item's own setting — vests yes,
    T-shirts no — and stays overridable per issue.

    Gated by the `merch.issue` approval policy (2026-08-27), default off —
    see `services/inventory/approvals.py`.
    """
    item = await db.get(Item, body.item_id)
    if item is None:
        raise HTTPException(404, detail="Item not found")
    recipient = await db.get(User, body.to_user_id)

    pending = await gate(
        db, action_type="merch.issue", actor=current_user,
        summary=f"Hand out {body.qty}x {item.name} to {recipient.full_name if recipient else 'someone'}",
        payload={
            "item_id": str(body.item_id), "to_user_id": str(body.to_user_id),
            "from_warehouse_id": str(body.from_warehouse_id), "qty": body.qty,
            "returnable": body.returnable,
            "due_back_on": body.due_back_on.isoformat() if body.due_back_on else None,
            "note": body.note,
        },
    )
    if pending:
        await db.commit()
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "pending_approval", "approval_request_id": str(pending.id)},
        )

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
    current_user: User = Depends(require_inventory_manage),
):
    """Gated by the `merch.return` approval policy (2026-08-27), default
    off — see `services/inventory/approvals.py`."""
    item = await db.get(Item, body.item_id)
    if item is None:
        raise HTTPException(404, detail="Item not found")
    giver = await db.get(User, body.from_user_id)

    held = {h["item_id"]: h["qty"] for h in await held_by_user(db, body.from_user_id)}
    if held.get(body.item_id, 0) < body.qty:
        raise HTTPException(409, detail=f"They only have {held.get(body.item_id, 0)} of those to give back")

    pending = await gate(
        db, action_type="merch.return", actor=current_user,
        summary=f"Take back {body.qty}x {item.name} from {giver.full_name if giver else 'someone'}",
        payload={
            "item_id": str(body.item_id), "from_user_id": str(body.from_user_id),
            "to_warehouse_id": str(body.to_warehouse_id), "qty": body.qty,
        },
    )
    if pending:
        await db.commit()
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "pending_approval", "approval_request_id": str(pending.id)},
        )

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
    _: User = Depends(require_storekeeper),
):
    return [HeldItemOut(**h) for h in await held_by_user(db, user_id)]


@router.get("/my-merch", response_model=list[HeldItemOut])
async def my_merch(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """What I'm holding, and what I owe back."""
    return [HeldItemOut(**h) for h in await held_by_user(db, current_user.id)]
