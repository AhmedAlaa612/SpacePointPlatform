"""The movement ledger — the one place anything physical changes hands.

Every write goes through `move()`. It records exactly one `Movement` row and
updates the denormalised state (`kits.current_*`, `stock_levels.qty`) in the
same transaction, so the ledger and the "where is it now" columns can never
disagree.

Raises `HTTPException` directly, matching this codebase's service convention
(see services/sessions/registration.py) — there is no domain-exception layer.
"""

import uuid
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.kit import Kit, KitItem
from app.models.inventory.movement import Movement
from app.models.inventory.stock import StockLevel
from app.models.inventory.warehouse import Warehouse

# `sold` is here from the start even though the shop is unbuilt: a kit leaving
# permanently is awkward to retrofit into a ledger that assumes return.
MOVEMENT_REASONS = {
    "issue",     # location -> person
    "return",    # person -> location
    "transfer",  # location -> location
    "refill",    # stock into a kit / to a warehouse
    "receive",   # goods in from a supplier (no `from`)
    "writeoff",  # gone: lost, broken beyond use
    "adjust",    # stocktake correction (no `from`/`to`)
    "sold",      # left permanently, paid for
}

# Reasons that legitimately have no destination.
_NO_DESTINATION_OK = {"writeoff", "adjust"}


async def move(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    reason: str,
    kit_id: uuid.UUID | None = None,
    item_id: uuid.UUID | None = None,
    qty: int | None = None,
    from_warehouse_id: uuid.UUID | None = None,
    from_user_id: uuid.UUID | None = None,
    from_kit_id: uuid.UUID | None = None,
    to_warehouse_id: uuid.UUID | None = None,
    to_user_id: uuid.UUID | None = None,
    to_kit_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    due_back_on: date | None = None,
    note: str | None = None,
) -> Movement:
    """Record one movement and apply its consequences.

    A kit move updates the kit's position. A bulk item move moves quantity
    between stock levels and/or in and out of a kit's contents. Both write the
    same row shape.

    Warehouse is the "where" a caller passes (2026-08-01) — a location can
    hold more than one warehouse, so `to_location_id`/`from_location_id` are
    no longer accepted here. The ledger row still records both: they're
    derived from the warehouse and stored alongside it, purely so the
    `movements` table stays readable ("Dubai" at a glance) without a join.
    """
    if reason not in MOVEMENT_REASONS:
        raise HTTPException(400, detail=f"Unknown movement reason '{reason}'")

    if (kit_id is None) == (item_id is None):
        raise HTTPException(400, detail="A movement is of exactly one kit or one item, not both or neither")

    destinations = [d for d in (to_warehouse_id, to_user_id, to_kit_id) if d is not None]
    if len(destinations) > 1:
        raise HTTPException(400, detail="A movement goes to one place: a warehouse, a person, or a kit")

    if not destinations and reason not in _NO_DESTINATION_OK:
        raise HTTPException(400, detail=f"A '{reason}' movement needs a destination")

    if kit_id is not None and (to_kit_id is not None or from_kit_id is not None):
        # A kit is not a component of another kit.
        raise HTTPException(400, detail="A kit cannot go inside a kit")

    if item_id is not None:
        if qty is None or qty <= 0:
            raise HTTPException(400, detail="Moving an item needs a positive quantity")
    elif qty is not None:
        raise HTTPException(400, detail="A kit is one thing — don't give it a quantity")

    if due_back_on is not None and to_user_id is None:
        # A due-back date on a warehouse-to-warehouse transfer is meaningless
        # and would put the row on the overdue list forever.
        raise HTTPException(400, detail="A return deadline only applies when something goes to a person")

    from_location_id = await _warehouse_location(db, from_warehouse_id)
    to_location_id = await _warehouse_location(db, to_warehouse_id)

    movement = Movement(
        id=uuid.uuid4(),
        kit_id=kit_id,
        item_id=item_id,
        qty=qty,
        from_location_id=from_location_id,
        from_warehouse_id=from_warehouse_id,
        from_user_id=from_user_id,
        from_kit_id=from_kit_id,
        to_location_id=to_location_id,
        to_warehouse_id=to_warehouse_id,
        to_user_id=to_user_id,
        to_kit_id=to_kit_id,
        session_id=session_id,
        reason=reason,
        due_back_on=due_back_on,
        note=note,
        created_by=actor_user_id,
    )
    db.add(movement)

    if kit_id is not None:
        await _apply_to_kit(db, kit_id, to_warehouse_id=to_warehouse_id, to_user_id=to_user_id)
    else:
        await _apply_to_stock(
            db, item_id=item_id, qty=qty,
            from_warehouse_id=from_warehouse_id, to_warehouse_id=to_warehouse_id,
            from_kit_id=from_kit_id, to_kit_id=to_kit_id,
        )

    await db.flush()
    return movement


async def _warehouse_location(db: AsyncSession, warehouse_id: uuid.UUID | None) -> uuid.UUID | None:
    if warehouse_id is None:
        return None
    return (await db.execute(
        select(Warehouse.location_id).where(Warehouse.id == warehouse_id)
    )).scalar_one_or_none()


async def _apply_to_kit(
    db: AsyncSession,
    kit_id: uuid.UUID,
    *,
    to_warehouse_id: uuid.UUID | None,
    to_user_id: uuid.UUID | None,
) -> None:
    kit = await db.get(Kit, kit_id)
    if kit is None:
        raise HTTPException(404, detail="Kit not found")

    if to_user_id is not None:
        # Out with a person. Warehouse is unchanged on purpose — the kit still
        # *belongs* to that warehouse, which is what keeps "what is in Dubai
        # Main" answerable while the kit is at a workshop. Holder set means "out".
        kit.current_holder_user_id = to_user_id
    elif to_warehouse_id is not None:
        # Arrived somewhere. Nobody holds a kit that is sitting on a shelf, so
        # this clears the holder — that is what makes a return a return.
        # `current_location_id` is derived, never set independently — see the
        # Kit model docstring.
        kit.current_warehouse_id = to_warehouse_id
        location_id = await _warehouse_location(db, to_warehouse_id)
        if location_id:
            kit.current_location_id = location_id
        kit.current_holder_user_id = None


async def _apply_to_stock(
    db: AsyncSession,
    *,
    item_id: uuid.UUID,
    qty: int,
    from_warehouse_id: uuid.UUID | None,
    to_warehouse_id: uuid.UUID | None,
    from_kit_id: uuid.UUID | None = None,
    to_kit_id: uuid.UUID | None = None,
) -> None:
    """Quantity leaves one side and arrives at the other. Either side can be a
    warehouse shelf (`stock_levels`) or the inside of a kit (`kit_items`)."""
    if from_warehouse_id is not None:
        level = await _level(db, item_id, from_warehouse_id)
        if level is None or level.qty < qty:
            available = 0 if level is None else level.qty
            raise HTTPException(
                409,
                detail=f"Not enough stock to move: {available} available, {qty} requested",
            )
        level.qty -= qty

    if from_kit_id is not None:
        contents = await _contents(db, item_id, from_kit_id)
        if contents is None or contents.qty < qty:
            available = 0 if contents is None else contents.qty
            raise HTTPException(
                409,
                detail=f"Kit does not have enough stock: {available} available, {qty} requested",
            )
        contents.qty -= qty
        if contents.qty == 0:
            await db.delete(contents)

    if to_warehouse_id is not None:
        level = await _level(db, item_id, to_warehouse_id)
        if level is None:
            level = StockLevel(id=uuid.uuid4(), item_id=item_id, warehouse_id=to_warehouse_id, qty=0)
            db.add(level)
        level.qty += qty

    if to_kit_id is not None:
        if await db.get(Kit, to_kit_id) is None:
            raise HTTPException(404, detail="Kit not found")
        contents = await _contents(db, item_id, to_kit_id)
        if contents is None:
            contents = KitItem(id=uuid.uuid4(), kit_id=to_kit_id, item_id=item_id, qty=0)
            db.add(contents)
        contents.qty += qty


async def _level(db: AsyncSession, item_id: uuid.UUID, warehouse_id: uuid.UUID) -> StockLevel | None:
    return (await db.execute(
        select(StockLevel).where(
            StockLevel.item_id == item_id, StockLevel.warehouse_id == warehouse_id
        )
    )).scalars().first()


async def _contents(db: AsyncSession, item_id: uuid.UUID, kit_id: uuid.UUID) -> KitItem | None:
    return (await db.execute(
        select(KitItem).where(KitItem.kit_id == kit_id, KitItem.item_id == item_id)
    )).scalars().first()


async def count_kit(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    kit_id: uuid.UUID,
    from_shelf: bool,
    reason: str,
    lines: list[tuple[uuid.UUID, int]],
) -> list[Movement]:
    """Set a kit's contents straight from a count — no shelf required.

    Takes the counted total per item, like `adjust_stock()`. `from_shelf`
    says whether the kit's own warehouse is the other end of each change:
    ticked is an ordinary `refill` (shelf -> kit or kit -> shelf, both are
    `move()` cases already); unticked is `receive` for an increase (arrived
    from nowhere in particular — a new kit built complete, goods unpacked
    straight into it) or `adjust` for a decrease (lost/miscounted, no
    destination — same as a stocktake correction on a shelf).

    One `Movement` per changed item, same as every other write here. Lines
    where the count didn't change are skipped, same convention as
    `adjust_stock()`'s zero-delta 409, just silently for a batch.

    `current_warehouse_id` is never null (a kit still belongs to a warehouse
    even while out with a person, see `_apply_to_kit`), so `from_shelf` is
    always resolvable — no separate "which warehouse" question to ask.
    """
    kit = await db.get(Kit, kit_id)
    if kit is None:
        raise HTTPException(404, detail="Kit not found")

    movements = []
    for item_id, new_qty in lines:
        current = await _contents(db, item_id, kit_id)
        delta = new_qty - (current.qty if current else 0)
        if delta == 0:
            continue
        if delta > 0:
            movements.append(await move(
                db, actor_user_id=actor_user_id, item_id=item_id, qty=delta,
                reason="refill" if from_shelf else "receive",
                from_warehouse_id=kit.current_warehouse_id if from_shelf else None,
                to_kit_id=kit_id, note=reason,
            ))
        else:
            movements.append(await move(
                db, actor_user_id=actor_user_id, item_id=item_id, qty=-delta,
                reason="refill" if from_shelf else "adjust",
                from_kit_id=kit_id,
                to_warehouse_id=kit.current_warehouse_id if from_shelf else None,
                note=reason,
            ))
    if not movements:
        raise HTTPException(409, detail="Nothing changed")
    return movements


async def confirm(db: AsyncSession, movement: Movement, *, actor_user_id: uuid.UUID) -> Movement:
    """The other party agrees this movement happened.

    Never a gate — the movement was already real when it was created. This
    exists so the *absence* of confirmation is visible: "ops marked it out but
    the instructor never confirmed collection" is the state worth surfacing.

    Idempotent: confirming twice keeps the first confirmation, because the
    first one is the true record of when agreement happened.
    """
    if movement.confirmed_at is None:
        movement.confirmed_by = actor_user_id
        movement.confirmed_at = datetime.now(timezone.utc)
        await db.flush()
    return movement


async def overdue(db: AsyncSession, *, as_of: date | None = None) -> list[Movement]:
    """Everything issued to a person, past its due date, not yet returned.

    "Not yet returned" is derived from the ledger rather than a flag on the
    row: a later movement with the same subject and that person as `from`
    closes it out. One less piece of state to keep honest.
    """
    as_of = as_of or date.today()

    out = (await db.execute(
        select(Movement).where(
            Movement.due_back_on.isnot(None),
            Movement.due_back_on < as_of,
            Movement.to_user_id.isnot(None),
        ).order_by(Movement.due_back_on)
    )).scalars().all()

    if not out:
        return []

    returns = (await db.execute(
        select(Movement.kit_id, Movement.item_id, Movement.from_user_id, Movement.created_at)
        .where(Movement.from_user_id.isnot(None))
    )).all()

    still_out = []
    for issue in out:
        returned = any(
            r_kit == issue.kit_id
            and r_item == issue.item_id
            and r_from == issue.to_user_id
            and r_at is not None
            and issue.created_at is not None
            and r_at >= issue.created_at
            for r_kit, r_item, r_from, r_at in returns
        )
        if not returned:
            still_out.append(issue)
    return still_out
