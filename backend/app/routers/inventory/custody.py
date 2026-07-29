"""Handover and merchandise endpoints (I2-3/I2-4).

The four custody legs, each a bulk action:

    POST /inventory/sessions/{id}/kits/issue     ops   → hands them out
    POST /inventory/sessions/{id}/kits/collected instr → confirms they have them
    POST /inventory/sessions/{id}/kits/return    instr → hands them back
    POST /inventory/sessions/{id}/kits/received  ops   → confirms, names where

Plus merchandise, which rides the same ledger.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations, require_session_delivery
from app.db.session import get_db
from app.models.user import User
from app.schemas.inventory.custody import (
    HeldItemOut,
    IssueMerchIn,
    IssueSessionKitsIn,
    ReturnMerchIn,
    ReturnSessionKitsIn,
    UnconfirmedHandoverOut,
)
from app.schemas.inventory.kits import MovementOut
from app.services.inventory import (
    confirm_collected,
    held_by_user,
    issue_merch,
    issue_session_kits,
    return_merch,
    return_session_kits,
    unconfirmed_handovers,
)
from app.services.sessions.delivery import _get_deliverable_session

router = APIRouter(prefix="/inventory", tags=["inventory-custody"])


# ── the four legs ───────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/kits/issue", response_model=list[MovementOut])
async def issue_kits(
    session_id: uuid.UUID,
    body: IssueSessionKitsIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Hand every assigned kit to whoever is teaching. Defaults to the lead
    instructor — asking again is friction for an answer we already have."""
    movements = await issue_session_kits(
        db,
        session_id=session_id,
        actor_user_id=current_user.id,
        to_user_id=body.to_user_id,
        due_back_on=body.due_back_on,
    )
    await db.commit()
    return movements


@router.post("/sessions/{session_id}/kits/collected", response_model=list[MovementOut])
async def confirm_kits_collected(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """"Yes, I have them." One tap, idempotent — tapping twice on a flaky
    connection must not be an error."""
    await _get_deliverable_session(db, session_id, current_user)
    movements = await confirm_collected(db, session_id=session_id, user_id=current_user.id)
    await db.commit()
    return movements


@router.post("/sessions/{session_id}/kits/return", response_model=list[MovementOut])
async def return_kits(
    session_id: uuid.UUID,
    body: ReturnSessionKitsIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Kits go back. A destination is required — a return without one leaves
    the register saying a kit is on a shelf without saying which."""
    await _get_deliverable_session(db, session_id, current_user)
    movements = await return_session_kits(
        db,
        session_id=session_id,
        actor_user_id=current_user.id,
        to_location_id=body.to_location_id,
    )
    if not movements:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="None of this session's kits are out")
    await db.commit()
    return movements


@router.get("/handovers/unconfirmed", response_model=list[UnconfirmedHandoverOut])
async def list_unconfirmed(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """Marked out, never acknowledged — usually a kit sitting in an office
    nobody collected it from. One of the two gaps the confirmation step
    exists to expose."""
    return [
        UnconfirmedHandoverOut(
            movement_id=m.id, kit_id=m.kit_id, item_id=m.item_id, qty=m.qty,
            to_user_id=m.to_user_id, to_user_name=name,
            due_back_on=m.due_back_on, created_at=m.created_at,
        )
        for m, name in await unconfirmed_handovers(db)
    ]


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
        from_location_id=body.from_location_id,
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
        to_location_id=body.to_location_id,
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
