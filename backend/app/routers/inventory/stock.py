"""Stock levels, stock movements and the movement ledger (I1-3).

The writes here — moving stock, adjusting a count, confirming a movement —
are `require_storekeeper`, which admits `storekeeper`, `operations`, or
`coo`.

**`GET /stock` and `GET /overdue` are `require_storekeeper` too** (fixed
2026-07-30). They were `require_operations`, which meant the storekeeper's
own landing page — the only page in their two-item sidebar — returned 403 for
every call it made and rendered "nothing on the shelves yet" no matter what
was on them. The role was unusable in practice from I1-4 until this was
caught in the browser.

**`GET /movements` (the full ledger) is `require_storekeeper` too now**
(widened 2026-08-27) — it used to stay ops-only on the theory that "nothing
a storekeeper does needs it," but the operator directive that day ("storekeeper
should read everything") settled that the other way; it's read-only, so
there's nothing to protect by withholding it.

What the role still *cannot* reach is writes outside its own job — kit
create/edit/delete, the catalogue, session assignments — enforced by
`require_inventory_manage` (in `kits.py`/`catalog.py`) simply not listing
`storekeeper`, pinned by
`test_a_storekeeper_cannot_touch_the_catalogue_or_the_kits`.

`coo` was added to `require_storekeeper` and given its own
`require_inventory_manage` (full write parity with `operations`, inventory-
domain only) on the same 2026-08-27 directive: "if I can see a page with my
role, I can use it" — no inventory page may show a control that then 403s
for a role that can reach the page.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_storekeeper
from app.db.session import get_db
from app.models.inventory.item import Item
from app.models.inventory.location import Location
from app.models.inventory.warehouse import Warehouse
from app.models.inventory.warehouse_cabin import ItemCabinAssignment, WarehouseCabin
from app.models.inventory.movement import Movement
from app.models.inventory.stock import StockLevel
from app.models.user import User
from app.schemas.inventory.kits import (
    ItemCabinBriefOut,
    MovementOut,
    StockAdjustBulkIn,
    StockAdjustIn,
    StockLevelOut,
    StockMoveIn,
)
from app.services import storage
from app.services.inventory import adjust_stock, confirm, move, overdue

router = APIRouter(prefix="/inventory", tags=["inventory-stock"])


@router.get("/stock", response_model=list[StockLevelOut])
async def list_stock(
    location_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_storekeeper),
):
    """`warehouse_id` is the real filter; `location_id` is a convenience that
    widens it to every warehouse under that location — stock is kept per
    warehouse (2026-08-01), a location can hold more than one."""
    stmt = (
        select(StockLevel, Item, Location, Warehouse)
        .join(Item, Item.id == StockLevel.item_id)
        .join(Warehouse, Warehouse.id == StockLevel.warehouse_id)
        .join(Location, Location.id == Warehouse.location_id)
        .order_by(Location.name, Warehouse.name, Item.name)
    )
    if location_id:
        stmt = stmt.where(Warehouse.location_id == location_id)
    if warehouse_id:
        stmt = stmt.where(StockLevel.warehouse_id == warehouse_id)
    if item_id:
        stmt = stmt.where(StockLevel.item_id == item_id)

    rows = (await db.execute(stmt)).all()

    # Load cabin assignments for the matching scope
    cabins_stmt = (
        select(
            ItemCabinAssignment.warehouse_id,
            ItemCabinAssignment.item_id,
            ItemCabinAssignment.cabin_id,
            WarehouseCabin.name.label("cabin_name"),
            ItemCabinAssignment.qty,
            ItemCabinAssignment.notes,
            ItemCabinAssignment.is_primary,
        )
        .join(WarehouseCabin, WarehouseCabin.id == ItemCabinAssignment.cabin_id)
        .order_by(WarehouseCabin.sort_order, WarehouseCabin.name)
    )
    if warehouse_id:
        cabins_stmt = cabins_stmt.where(ItemCabinAssignment.warehouse_id == warehouse_id)
    if item_id:
        cabins_stmt = cabins_stmt.where(ItemCabinAssignment.item_id == item_id)

    cabin_rows = (await db.execute(cabins_stmt)).all()
    cabins_by_stock: dict[tuple[uuid.UUID, uuid.UUID], list[ItemCabinBriefOut]] = {}
    for wh_id, it_id, cab_id, cab_name, c_qty, c_notes, c_primary in cabin_rows:
        cabins_by_stock.setdefault((wh_id, it_id), []).append(
            ItemCabinBriefOut(
                cabin_id=cab_id,
                cabin_name=cab_name,
                qty=c_qty,
                notes=c_notes,
                is_primary=c_primary,
            )
        )

    out_list = []
    for level, item, location, wh in rows:
        img_url = (
            await storage.resolve_url(item.image_bucket, item.image_path)
            if item.image_bucket and item.image_path
            else None
        )
        out_list.append(
            StockLevelOut(
                item_id=item.id,
                item_name=item.name,
                category=item.category,
                subcategory=item.subcategory,
                image_url=img_url,
                location_id=location.id,
                location_name=location.name,
                warehouse_id=wh.id,
                warehouse_name=wh.name,
                qty=level.qty,
                cabins=cabins_by_stock.get((wh.id, item.id), []),
            )
        )
    return out_list


@router.post("/stock/move", response_model=MovementOut, status_code=status.HTTP_201_CREATED)
async def move_stock(
    body: StockMoveIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_storekeeper),
):
    """Move a quantity of one item. A refill into a kit is
    `from_warehouse_id` + `to_kit_id`; receiving goods has no source."""
    movement = await move(
        db,
        actor_user_id=current_user.id,
        reason=body.reason,
        item_id=body.item_id,
        qty=body.qty,
        from_warehouse_id=body.from_warehouse_id,
        from_kit_id=body.from_kit_id,
        to_warehouse_id=body.to_warehouse_id,
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
    if await db.get(Warehouse, body.warehouse_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown warehouse")

    movement = await adjust_stock(
        db,
        actor_user_id=current_user.id,
        item_id=body.item_id,
        warehouse_id=body.warehouse_id,
        new_qty=body.new_qty,
        reason=body.reason,
    )
    await db.commit()
    await db.refresh(movement)
    return movement


@router.post("/stock/adjust-bulk", response_model=list[MovementOut], status_code=status.HTTP_201_CREATED)
async def adjust_bulk(
    body: StockAdjustBulkIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_storekeeper),
):
    """One stocktake, many item/warehouse counts, one reason. Loops the same
    `adjust_stock()` a single correction uses, in one transaction, skipping
    rows where the count didn't change instead of failing the whole save on
    the first one (`adjust_stock`'s own 409)."""
    for line in body.levels:
        if await db.get(Item, line.item_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown item")
        if await db.get(Warehouse, line.warehouse_id) is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown warehouse")

    movements = []
    for line in body.levels:
        try:
            movements.append(await adjust_stock(
                db,
                actor_user_id=current_user.id,
                item_id=line.item_id,
                warehouse_id=line.warehouse_id,
                new_qty=line.new_qty,
                reason=body.reason,
            ))
        except HTTPException as e:
            if e.status_code == status.HTTP_409_CONFLICT:
                continue
            raise

    if not movements:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Nothing changed")

    await db.commit()
    for m in movements:
        await db.refresh(m)
    return movements


# ── the ledger ──────────────────────────────────────────────────────────────

@router.get("/movements", response_model=list[MovementOut])
async def list_movements(
    kit_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    unconfirmed_only: bool = False,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_storekeeper),
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
    _: User = Depends(require_storekeeper),
):
    """Issued to a person, past its due date, not yet returned. Nothing
    without a deadline ever appears — otherwise the list becomes noise and
    stops being read."""
    return await overdue(db, as_of=as_of)
