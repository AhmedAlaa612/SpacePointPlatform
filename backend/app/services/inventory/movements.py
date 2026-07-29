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

from app.models.inventory.kit import Kit
from app.models.inventory.movement import Movement
from app.models.inventory.stock import StockLevel

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
    from_location_id: uuid.UUID | None = None,
    from_user_id: uuid.UUID | None = None,
    to_location_id: uuid.UUID | None = None,
    to_user_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    due_back_on: date | None = None,
    note: str | None = None,
) -> Movement:
    """Record one movement and apply its consequences.

    A kit move updates the kit's position. A bulk item move moves quantity
    between stock levels. Both write the same row shape.
    """
    if reason not in MOVEMENT_REASONS:
        raise HTTPException(400, detail=f"Unknown movement reason '{reason}'")

    if (kit_id is None) == (item_id is None):
        raise HTTPException(400, detail="A movement is of exactly one kit or one item, not both or neither")

    if to_location_id is not None and to_user_id is not None:
        raise HTTPException(400, detail="A movement goes to a location or a person, not both")

    if to_location_id is None and to_user_id is None and reason not in _NO_DESTINATION_OK:
        raise HTTPException(400, detail=f"A '{reason}' movement needs a destination")

    if item_id is not None:
        if qty is None or qty <= 0:
            raise HTTPException(400, detail="Moving an item needs a positive quantity")
    elif qty is not None:
        raise HTTPException(400, detail="A kit is one thing — don't give it a quantity")

    if due_back_on is not None and to_user_id is None:
        # A due-back date on a warehouse-to-warehouse transfer is meaningless
        # and would put the row on the overdue list forever.
        raise HTTPException(400, detail="A return deadline only applies when something goes to a person")

    movement = Movement(
        id=uuid.uuid4(),
        kit_id=kit_id,
        item_id=item_id,
        qty=qty,
        from_location_id=from_location_id,
        from_user_id=from_user_id,
        to_location_id=to_location_id,
        to_user_id=to_user_id,
        session_id=session_id,
        reason=reason,
        due_back_on=due_back_on,
        note=note,
        created_by=actor_user_id,
    )
    db.add(movement)

    if kit_id is not None:
        await _apply_to_kit(db, kit_id, to_location_id=to_location_id, to_user_id=to_user_id)
    else:
        await _apply_to_stock(
            db, item_id=item_id, qty=qty,
            from_location_id=from_location_id, to_location_id=to_location_id,
        )

    await db.flush()
    return movement


async def _apply_to_kit(
    db: AsyncSession,
    kit_id: uuid.UUID,
    *,
    to_location_id: uuid.UUID | None,
    to_user_id: uuid.UUID | None,
) -> None:
    kit = await db.get(Kit, kit_id)
    if kit is None:
        raise HTTPException(404, detail="Kit not found")

    if to_user_id is not None:
        # Out with a person. Location is unchanged on purpose — the kit still
        # *belongs* to that warehouse, which is what keeps "what is in Dubai"
        # answerable while the kit is at a workshop. Holder set means "out".
        kit.current_holder_user_id = to_user_id
    elif to_location_id is not None:
        # Arrived somewhere. Nobody holds a kit that is sitting on a shelf, so
        # this clears the holder — that is what makes a return a return.
        kit.current_location_id = to_location_id
        kit.current_holder_user_id = None


async def _apply_to_stock(
    db: AsyncSession,
    *,
    item_id: uuid.UUID,
    qty: int,
    from_location_id: uuid.UUID | None,
    to_location_id: uuid.UUID | None,
) -> None:
    if from_location_id is not None:
        level = await _level(db, item_id, from_location_id)
        if level is None or level.qty < qty:
            available = 0 if level is None else level.qty
            raise HTTPException(
                409,
                detail=f"Not enough stock to move: {available} available, {qty} requested",
            )
        level.qty -= qty

    if to_location_id is not None:
        level = await _level(db, item_id, to_location_id)
        if level is None:
            level = StockLevel(id=uuid.uuid4(), item_id=item_id, location_id=to_location_id, qty=0)
            db.add(level)
        level.qty += qty


async def _level(db: AsyncSession, item_id: uuid.UUID, location_id: uuid.UUID) -> StockLevel | None:
    return (await db.execute(
        select(StockLevel).where(
            StockLevel.item_id == item_id, StockLevel.location_id == location_id
        )
    )).scalars().first()


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
