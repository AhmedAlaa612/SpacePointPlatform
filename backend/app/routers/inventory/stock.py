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

`/stock/adjust` and `/stock/adjust-bulk` are additionally gated by the
`stock.adjust` approval policy (2026-08-27 follow-up, default off) — see
`services/inventory/approvals.py`. Gated for anyone who isn't coo/admin,
this returns a 202 with a pending-request id instead of a 201, and nothing
changes until approved.
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_storekeeper
from app.db.session import get_db
from app.models.inventory.item import Item
from app.models.inventory.location import Location
from app.models.inventory.warehouse import Warehouse
from app.models.inventory.movement import Movement
from app.models.inventory.stock import StockLevel
from app.models.user import User
from app.schemas.inventory.kits import (
    MovementOut,
    StockAdjustBulkIn,
    StockAdjustIn,
    StockLevelOut,
    StockMoveIn,
)
from app.services.inventory import adjust_stock, confirm, gate, move, overdue

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
    return [
        StockLevelOut(
            item_id=item.id,
            item_name=item.name,
            category=item.category,
            location_id=location.id,
            location_name=location.name,
            warehouse_id=wh.id,
            warehouse_name=wh.name,
            qty=level.qty,
        )
        for level, item, location, wh in rows
    ]


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
    """Correct a stock level to the counted total. Reason is mandatory.

    Gated by the `stock.adjust` approval policy (2026-08-27), default off —
    see `services/inventory/approvals.py`. Same policy/action type as
    `/stock/adjust-bulk` below, since both just loop `adjust_stock()`; turning
    this gate on queues *every* correction, routine stocktakes included —
    there's no code-level distinction between a stocktake and an override.
    """
    item = await db.get(Item, body.item_id)
    if item is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown item")
    warehouse = await db.get(Warehouse, body.warehouse_id)
    if warehouse is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown warehouse")

    pending = await gate(
        db, action_type="stock.adjust", actor=current_user,
        summary=f"Correct {item.name} at {warehouse.name} to {body.new_qty} ({body.reason})",
        payload={"reason": body.reason, "lines": [
            {"item_id": str(body.item_id), "warehouse_id": str(body.warehouse_id), "new_qty": body.new_qty},
        ]},
    )
    if pending:
        await db.commit()
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "pending_approval", "approval_request_id": str(pending.id)},
        )

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
    the first one (`adjust_stock`'s own 409).

    Gated by the same `stock.adjust` policy as the single-line endpoint
    above — one pending request for the whole stocktake, not one per line.
    """
    items, warehouses = {}, {}
    for line in body.levels:
        items[line.item_id] = items.get(line.item_id) or await db.get(Item, line.item_id)
        if items[line.item_id] is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown item")
        warehouses[line.warehouse_id] = warehouses.get(line.warehouse_id) or await db.get(Warehouse, line.warehouse_id)
        if warehouses[line.warehouse_id] is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown warehouse")

    pending = await gate(
        db, action_type="stock.adjust", actor=current_user,
        summary=f"Stocktake correction — {len(body.levels)} line(s) ({body.reason})",
        payload={"reason": body.reason, "lines": [
            {"item_id": str(line.item_id), "warehouse_id": str(line.warehouse_id), "new_qty": line.new_qty}
            for line in body.levels
        ]},
    )
    if pending:
        await db.commit()
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"status": "pending_approval", "approval_request_id": str(pending.id)},
        )

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
