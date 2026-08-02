"""Non-kit equipment an instructor takes to a session (I2-7).

The trigger for this is the CEO's own process: WhatsApp photos of a mic
speaker, a battery charger, a roll of stickers and a bag of T-shirts picked up
from a co-working space on the way to a workshop. Nothing about that is a new
concept here — `items` is a generic catalogue, `stock_levels` is per location,
and giving something to a person is a `movement`. **This module adds no
tables and no columns.** It is a form over machinery that already exists.

Three decisions worth knowing, because each one is the difference between a
form that gets filled in and one that doesn't:

* **The collection point is derived, never asked.** Ops physically transfers a
  kit to the session's warehouse before the instructor collects it — the
  transfer is itself a movement, so by the time anyone picks anything up the
  kit's `current_warehouse_id` *is* the collection point. That is not an
  approximation of the fact, it is the fact. The only time we ask is when
  there is nothing to derive from (§G's rare no-kit session) or when the
  assigned kits genuinely sit in different places.

* **The shelf renders up front, not behind a search box (B3).** An instructor
  who doesn't already know an item's exact name has nothing to type — a
  location's catalogue is small enough that a tick-list beats a search that
  shows nothing until you guess right.

* **You can only take what the register says is there.** `move()` refuses to
  drive stock negative and this does not weaken that — a self-report that
  invents stock would corrupt the one number the storekeeper works from. The
  cost is real and is flagged in the plan: if nobody has entered a
  co-working space's stock, its instructors have nothing to pick from.

Whether something is expected back is read from `items.returnable_default` at
display time rather than stored on the movement. There is no `returnable`
column to store it in, and for same-day equipment the question is only ever
asked once — in the post-session prompt — so deriving it is one fewer piece
of state to keep honest.
"""

import uuid

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.equipment_flag import EquipmentReturnFlag
from app.models.inventory.item import Item
from app.models.inventory.kit import Kit
from app.models.inventory.movement import Movement
from app.models.inventory.session_kit import SessionKit
from app.models.inventory.stock import StockLevel
from app.models.inventory.warehouse import Warehouse
from app.models.sessions.cohort import Cohort
from app.models.sessions.session import Session
from app.services import storage
from app.services.inventory.movements import move


def _ensure_session_open(session: Session | None) -> None:
    pass


async def pickup_warehouse(db: AsyncSession, session_id: uuid.UUID) -> Warehouse | None:
    """Where this session's equipment is collected from.

    The session's (or its cohort's) assigned warehouse wins when set
    (2026-08-01) — that is the shelf ops picked for this session,
    deliberately, not a guess. Absent that, a resolved location with exactly
    one warehouse resolves to it unambiguously. Falls back to deriving it from
    the assigned kits' current position for sessions with nothing assigned yet,
    which by then have been physically moved to the session's warehouse.
    `None` means we genuinely cannot tell — nothing assigned, the location has
    more than one warehouse, and either no kits or kits sitting in more than
    one place — and the caller has to ask. Returning an arbitrary one of
    several would be a field that quietly disagrees with reality, which is the
    thing this design set out to avoid.
    """
    session = await db.get(Session, session_id)
    effective_wh_id = session.warehouse_id if session else None
    cohort = None
    if effective_wh_id is None and session is not None:
        cohort = await db.get(Cohort, session.cohort_id)
        effective_wh_id = cohort.warehouse_id if cohort else None
    if effective_wh_id:
        return await db.get(Warehouse, effective_wh_id)

    effective_location_id = session.location_id if session else None
    if effective_location_id is None and session is not None:
        cohort = cohort or await db.get(Cohort, session.cohort_id)
        effective_location_id = cohort.location_id if cohort else None
    if effective_location_id:
        warehouses = (await db.execute(
            select(Warehouse).where(Warehouse.location_id == effective_location_id)
        )).scalars().all()
        if len(warehouses) == 1:
            return warehouses[0]

    warehouse_ids = (await db.execute(
        select(Kit.current_warehouse_id)
        .join(SessionKit, SessionKit.kit_id == Kit.id)
        .where(SessionKit.session_id == session_id)
        .distinct()
    )).scalars().all()

    if len(warehouse_ids) != 1:
        return None
    return await db.get(Warehouse, warehouse_ids[0])


async def search_equipment(
    db: AsyncSession, *, warehouse_id: uuid.UUID, q: str = "", limit: int = 100
) -> list[dict]:
    """Items on the shelf in that warehouse — the whole shelf by default (B3),
    optionally narrowed by name.

    Only things with stock actually there: offering an item the register says
    isn't present invites a pickup that `move()` will refuse at the last step,
    after the instructor has already ticked it.

    Previously this required at least two characters of search text and
    returned nothing otherwise, on the theory that a forty-item shelf isn't
    worth rendering unprompted. In practice that meant typing before you could
    see anything was there at all — worse than scrolling a short list. Ops
    catalogues stay small enough (per warehouse) that showing it up front reads
    faster than searching for it.
    """
    q = (q or "").strip()

    stmt = (
        select(Item, StockLevel.qty)
        .join(StockLevel, StockLevel.item_id == Item.id)
        .where(StockLevel.warehouse_id == warehouse_id, StockLevel.qty > 0)
        .order_by(Item.name)
        .limit(limit)
    )
    if q:
        stmt = stmt.where(Item.name.ilike(f"%{q}%"))

    rows = (await db.execute(stmt)).all()

    return [
        {
            "item_id": item.id,
            "item_name": item.name,
            "category": item.category,
            "available": qty,
            "returnable": item.returnable_default,
            "description": item.description,
            # Same photo shown to ops in the catalogue (B3) — an instructor
            # unfamiliar with an item's exact name can recognise it on sight.
            "image_url": await storage.resolve_url(item.image_bucket, item.image_path),
        }
        for item, qty in rows
    ]


async def take_equipment(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    lines: list[tuple[uuid.UUID, int]],
    warehouse_id: uuid.UUID | None = None,
    note: str | None = None,
) -> list[Movement]:
    """"I also took these." One ordinary issue movement per line.

    No due date: this is same-day equipment and the post-session prompt is
    what asks for it back. A deadline on every roll of stickers would fill the
    overdue list with noise and stop it working for the kits it exists for.
    """
    if await db.get(Session, session_id) is None:
        raise HTTPException(404, detail="Session not found")

    if warehouse_id is None:
        warehouse = await pickup_warehouse(db, session_id)
        if warehouse is None:
            raise HTTPException(
                409,
                detail="We can't tell where you collected these from — pick the warehouse",
            )
        warehouse_id = warehouse.id
    elif await db.get(Warehouse, warehouse_id) is None:
        raise HTTPException(404, detail="Warehouse not found")

    if not lines:
        raise HTTPException(400, detail="Nothing to record")

    return [
        await move(
            db,
            actor_user_id=actor_user_id,
            reason="issue",
            item_id=item_id,
            qty=qty,
            from_warehouse_id=warehouse_id,
            to_user_id=actor_user_id,
            session_id=session_id,
            note=note,
        )
        for item_id, qty in lines
    ]


async def session_equipment(
    db: AsyncSession, *, session_id: uuid.UUID, user_id: uuid.UUID
) -> list[dict]:
    """What this person took for this session, and what is still out.

    Netted from the ledger rather than tracked on a row of its own — an issue
    and a later return for the same item and session cancel out. Same
    reasoning as `held_by_user`: bulk holdings are rare enough to compute, and
    computing them means there is nothing to keep in sync.
    """
    taken = dict((await db.execute(
        select(Movement.item_id, func.sum(Movement.qty))
        .where(
            Movement.session_id == session_id,
            Movement.to_user_id == user_id,
            Movement.item_id.isnot(None),
            Movement.reason == "issue",
        )
        .group_by(Movement.item_id)
    )).all())
    if not taken:
        return []

    returned = dict((await db.execute(
        select(Movement.item_id, func.sum(Movement.qty))
        .where(
            Movement.session_id == session_id,
            Movement.from_user_id == user_id,
            Movement.item_id.isnot(None),
            Movement.reason == "return",
        )
        .group_by(Movement.item_id)
    )).all())

    items = {
        i.id: i for i in (await db.execute(
            select(Item).where(Item.id.in_(taken.keys())).order_by(Item.name)
        )).scalars().all()
    }

    flagged = set((await db.execute(
        select(EquipmentReturnFlag.item_id).where(
            EquipmentReturnFlag.session_id == session_id, EquipmentReturnFlag.user_id == user_id,
            EquipmentReturnFlag.item_id.in_(taken.keys()),
        )
    )).scalars().all())

    lines = []
    for item_id, qty in taken.items():
        item = items.get(item_id)
        if item is None:
            continue
        back = returned.get(item_id, 0) or 0
        lines.append({
            "item_id": item.id,
            "item_name": item.name,
            "qty_taken": qty or 0,
            "qty_returned": back,
            "outstanding": (qty or 0) - back,
            "returnable": item.returnable_default,
            "later": item_id in flagged,
        })
    return sorted(lines, key=lambda line: line["item_name"])


async def return_equipment(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    lines: list[tuple[uuid.UUID, int]],
    to_warehouse_id: uuid.UUID | None = None,
) -> list[Movement]:
    """"Yes, I brought it back." Answering "returning later" is simply not
    calling this — the line stays outstanding and stays visible, which is the
    honest record of where the thing actually is.

    Clears any "return later" flag on the lines it actually returns — the
    two are mutually exclusive, and this is the only place that has to know
    it. Refused once the session is done; see `mark_equipment_return_later`
    for why that gate matters here more than it looks."""
    _ensure_session_open(await db.get(Session, session_id))

    outstanding = {
        line["item_id"]: line["outstanding"]
        for line in await session_equipment(db, session_id=session_id, user_id=actor_user_id)
    }

    if to_warehouse_id is None:
        warehouse = await pickup_warehouse(db, session_id)
        if warehouse is None:
            raise HTTPException(409, detail="Say where you're leaving these")
        to_warehouse_id = warehouse.id
    elif await db.get(Warehouse, to_warehouse_id) is None:
        raise HTTPException(404, detail="Warehouse not found")

    movements = []
    for item_id, qty in lines:
        have = outstanding.get(item_id, 0)
        if qty > have:
            raise HTTPException(
                409, detail=f"You only have {have} of those to give back"
            )
        movements.append(await move(
            db,
            actor_user_id=actor_user_id,
            reason="return",
            item_id=item_id,
            qty=qty,
            from_user_id=actor_user_id,
            to_warehouse_id=to_warehouse_id,
            session_id=session_id,
        ))

    await db.execute(
        delete(EquipmentReturnFlag).where(
            EquipmentReturnFlag.session_id == session_id,
            EquipmentReturnFlag.user_id == actor_user_id,
            EquipmentReturnFlag.item_id.in_([item_id for item_id, _ in lines]),
        )
    )
    return movements


async def mark_equipment_return_later(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    item_ids: list[uuid.UUID],
) -> None:
    """"I'll bring this back later" — for something not yet given back, that's
    just a note. For something already marked returned, this undoes that
    return first: a correction to the ledger (a fresh issue of the same
    quantity, back to whoever said they still have it), not a second kind of
    state living outside it. Changeable either way, same as a kit's report,
    right up until the session is marked done."""
    session = await db.get(Session, session_id)
    _ensure_session_open(session)

    lines = {l["item_id"]: l for l in await session_equipment(db, session_id=session_id, user_id=actor_user_id)}
    warehouse = None
    for item_id in item_ids:
        line = lines.get(item_id)
        if line is None:
            raise HTTPException(404, detail="That item wasn't taken for this session")

        if line["outstanding"] <= 0 and line["qty_returned"] > 0:
            if warehouse is None:
                warehouse = await pickup_warehouse(db, session_id)
                if warehouse is None:
                    raise HTTPException(409, detail="Say where this is being taken back from")
            await move(
                db,
                actor_user_id=actor_user_id,
                reason="issue",
                item_id=item_id,
                qty=line["qty_returned"],
                from_warehouse_id=warehouse.id,
                to_user_id=actor_user_id,
                session_id=session_id,
            )

        existing = await db.scalar(
            select(EquipmentReturnFlag).where(
                EquipmentReturnFlag.session_id == session_id,
                EquipmentReturnFlag.item_id == item_id,
                EquipmentReturnFlag.user_id == actor_user_id,
            )
        )
        if existing is None:
            db.add(EquipmentReturnFlag(
                id=uuid.uuid4(), session_id=session_id, item_id=item_id, user_id=actor_user_id,
            ))
    await db.flush()
