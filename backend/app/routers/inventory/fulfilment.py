"""The storekeeper's fulfilment queue (I3-1).

    GET /inventory/fulfilment                        what is short, and can I fix it
    POST /inventory/fulfilment/{kit_id}/fulfil       put parts back in the box
    PUT  /inventory/fulfilment/{kit_id}/awaiting     I looked; the shelf was empty

**Everything here is `require_storekeeper`**, which admits `storekeeper` or
`operations`. Deliberately mounted under `/inventory/fulfilment` rather than
as more `/inventory/kits/{id}/...` routes: every path under `/inventory/kits`
is `require_operations`, and keeping that true means the boundary can be read
off the URL instead of checked route by route. The storekeeper's narrowness
is invisible negative space — `test_a_storekeeper_cannot_touch_the_catalogue_
or_the_kits` is what pins it — so the fewer exceptions inside that namespace,
the better.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_storekeeper
from app.db.session import get_db
from app.models.inventory.kit import Kit
from app.models.user import User
from app.schemas.inventory.fulfilment import (
    AwaitingPartsIn,
    FulfilKitIn,
    FulfilmentKitOut,
)
from app.schemas.inventory.kits import MovementOut
from app.services.inventory import (
    fulfil_kit,
    fulfilment_queue,
    set_awaiting_parts,
)

router = APIRouter(prefix="/inventory", tags=["inventory-fulfilment"])


async def _kit_or_404(db: AsyncSession, kit_id: uuid.UUID) -> Kit:
    kit = await db.get(Kit, kit_id)
    if kit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kit not found")
    return kit


@router.get("/fulfilment", response_model=list[FulfilmentKitOut])
async def get_fulfilment_queue(
    location_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_storekeeper),
):
    """Kits that are short something, with how many of each are on the shelf
    where the kit is. Retired and lost kits are left out — chasing parts for a
    box that is gone is the kind of noise that stops a list being read."""
    return [FulfilmentKitOut(**row) for row in await fulfilment_queue(db, location_id=location_id)]


@router.post(
    "/fulfilment/{kit_id}/fulfil",
    response_model=list[MovementOut],
    status_code=status.HTTP_201_CREATED,
)
async def fulfil(
    kit_id: uuid.UUID,
    body: FulfilKitIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_storekeeper),
):
    """Move parts off a shelf and into the kit — an ordinary `refill`
    movement, so stock and kit contents change in one transaction."""
    kit = await _kit_or_404(db, kit_id)
    movements = await fulfil_kit(
        db,
        kit=kit,
        lines=[(line.item_id, line.qty) for line in body.lines],
        actor_user_id=current_user.id,
        from_warehouse_id=body.from_warehouse_id,
    )
    await db.commit()
    return movements


@router.put("/fulfilment/{kit_id}/awaiting", response_model=FulfilmentKitOut)
async def set_awaiting(
    kit_id: uuid.UUID,
    body: AwaitingPartsIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_storekeeper),
):
    """"I looked, and there were none." The one fact in this loop that cannot
    be derived — stock can be replenished tomorrow, so an empty shelf now is
    not the same thing as somebody having checked."""
    kit = await _kit_or_404(db, kit_id)
    await set_awaiting_parts(db, kit=kit, awaiting=body.awaiting, note=body.note)
    await db.commit()

    for row in await fulfilment_queue(db):
        if row["kit_id"] == kit_id:
            return FulfilmentKitOut(**row)
    # Clearing the flag on a kit that is no longer short drops it off the
    # queue entirely — which is the correct outcome, not an error.
    raise HTTPException(
        status.HTTP_409_CONFLICT, detail="This kit is no longer short of anything"
    )
