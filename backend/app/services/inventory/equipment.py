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
  kit's `current_location_id` *is* the collection point. That is not an
  approximation of the fact, it is the fact. The only time we ask is when
  there is nothing to derive from (§G's rare no-kit session) or when the
  assigned kits genuinely sit in different places.

* **Search starts empty and never renders the shelf.** A co-working space may
  hold forty item types and most sessions take nothing extra. Scrolling forty
  rows on a phone to tick two is exactly how a form stops being filled.

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
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.item import Item
from app.models.inventory.kit import Kit
from app.models.inventory.location import Location
from app.models.inventory.movement import Movement
from app.models.inventory.session_kit import SessionKit
from app.models.inventory.stock import StockLevel
from app.models.sessions.session import Session
from app.services.inventory.movements import move

# Below this, a search matches most of the catalogue and stops being a search.
MIN_SEARCH_CHARS = 2


async def pickup_location(db: AsyncSession, session_id: uuid.UUID) -> Location | None:
    """Where this session's equipment is collected from.

    Derived from the assigned kits, which by then have been physically moved
    to the session's warehouse. `None` means we genuinely cannot tell — either
    no kits are assigned, or they are sitting in more than one place — and the
    caller has to ask. Returning an arbitrary one of several would be a field
    that quietly disagrees with reality, which is the thing this design set out
    to avoid.
    """
    location_ids = (await db.execute(
        select(Kit.current_location_id)
        .join(SessionKit, SessionKit.kit_id == Kit.id)
        .where(SessionKit.session_id == session_id)
        .distinct()
    )).scalars().all()

    if len(location_ids) != 1:
        return None
    return await db.get(Location, location_ids[0])


async def search_equipment(
    db: AsyncSession, *, location_id: uuid.UUID, q: str, limit: int = 20
) -> list[dict]:
    """Items on the shelf at that location whose name matches.

    Only things with stock actually there: offering an item the register says
    isn't present invites a pickup that `move()` will refuse at the last step,
    after the instructor has already typed it in.
    """
    q = (q or "").strip()
    if len(q) < MIN_SEARCH_CHARS:
        return []

    rows = (await db.execute(
        select(Item, StockLevel.qty)
        .join(StockLevel, StockLevel.item_id == Item.id)
        .where(
            StockLevel.location_id == location_id,
            StockLevel.qty > 0,
            Item.name.ilike(f"%{q}%"),
        )
        .order_by(Item.name)
        .limit(limit)
    )).all()

    return [
        {
            "item_id": item.id,
            "item_name": item.name,
            "category": item.category,
            "available": qty,
            "returnable": item.returnable_default,
        }
        for item, qty in rows
    ]


async def take_equipment(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    lines: list[tuple[uuid.UUID, int]],
    location_id: uuid.UUID | None = None,
    note: str | None = None,
) -> list[Movement]:
    """"I also took these." One ordinary issue movement per line.

    No due date: this is same-day equipment and the post-session prompt is
    what asks for it back. A deadline on every roll of stickers would fill the
    overdue list with noise and stop it working for the kits it exists for.
    """
    if await db.get(Session, session_id) is None:
        raise HTTPException(404, detail="Session not found")

    if location_id is None:
        location = await pickup_location(db, session_id)
        if location is None:
            raise HTTPException(
                409,
                detail="We can't tell where you collected these from — pick the place",
            )
        location_id = location.id
    elif await db.get(Location, location_id) is None:
        raise HTTPException(404, detail="Location not found")

    if not lines:
        raise HTTPException(400, detail="Nothing to record")

    return [
        await move(
            db,
            actor_user_id=actor_user_id,
            reason="issue",
            item_id=item_id,
            qty=qty,
            from_location_id=location_id,
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
        })
    return sorted(lines, key=lambda line: line["item_name"])


async def return_equipment(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    lines: list[tuple[uuid.UUID, int]],
    to_location_id: uuid.UUID | None = None,
) -> list[Movement]:
    """"Yes, I brought it back." Answering "returning later" is simply not
    calling this — the line stays outstanding and stays visible, which is the
    honest record of where the thing actually is."""
    outstanding = {
        line["item_id"]: line["outstanding"]
        for line in await session_equipment(db, session_id=session_id, user_id=actor_user_id)
    }

    if to_location_id is None:
        location = await pickup_location(db, session_id)
        if location is None:
            raise HTTPException(409, detail="Say where you're leaving these")
        to_location_id = location.id
    elif await db.get(Location, to_location_id) is None:
        raise HTTPException(404, detail="Location not found")

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
            to_location_id=to_location_id,
            session_id=session_id,
        ))
    return movements
