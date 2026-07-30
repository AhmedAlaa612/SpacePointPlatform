"""Handing things over, and getting them back (I2-3/I2-4).

Custody has four legs, and each one is asserted by one party and optionally
confirmed by the other:

    ops marks out       →  instructor confirms collected
    instructor hands back →  ops confirms received (and says where it went)

**The gaps are the product.** A movement is real the moment it is created, so
confirmation never blocks anything — but *out and never collected* and *handed
back and never received* are exactly where things go missing, and both fall
out of the absence of a confirmation without any extra state.

Everything here works in bulk. Five kits at four taps each is twenty taps, and
a workflow that costs twenty taps is one people stop doing.
"""

import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.item import Item
from app.models.inventory.kit import Kit
from app.models.inventory.movement import Movement
from app.models.inventory.session_kit import SessionKit
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.inventory.movements import move
from app.services.sessions.openings import session_lead_user_id


async def issue_session_kits(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    to_user_id: uuid.UUID | None = None,
    due_back_on: date | None = None,
) -> list[Movement]:
    """Hand every kit assigned to a session to the person teaching it.

    `to_user_id` defaults to the session's lead instructor, because that is
    the answer in almost every case and asking again is friction for nothing.
    """
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, detail="Session not found")

    if to_user_id is None:
        # I5-3: "the lead" is the most senior *role* (lowest sort_order), not a
        # string match on "lead" — roles are configurable now, so matching a
        # name would break the moment someone renames or reorders them.
        to_user_id = await session_lead_user_id(db, session_id)
    if to_user_id is None:
        raise HTTPException(
            409, detail="Nobody is assigned to teach this session yet — assign an instructor first"
        )

    kits = (await db.execute(
        select(Kit).join(SessionKit, SessionKit.kit_id == Kit.id)
        .where(SessionKit.session_id == session_id).order_by(Kit.label)
    )).scalars().all()
    if not kits:
        raise HTTPException(409, detail="No kits are assigned to this session")

    movements = []
    for kit in kits:
        if kit.current_holder_user_id == to_user_id:
            continue  # already with them; re-issuing would be a duplicate row
        movements.append(await move(
            db,
            actor_user_id=actor_user_id,
            reason="issue",
            kit_id=kit.id,
            from_location_id=kit.current_location_id,
            to_user_id=to_user_id,
            session_id=session_id,
            due_back_on=due_back_on,
        ))
    return movements


async def confirm_collected(
    db: AsyncSession, *, session_id: uuid.UUID, user_id: uuid.UUID
) -> list[Movement]:
    """The instructor agrees they physically have the kits.

    Idempotent, and silent about movements already confirmed — this is a
    one-tap action on a phone, and tapping it twice must not be an error.
    """
    pending = (await db.execute(
        select(Movement).where(
            Movement.session_id == session_id,
            Movement.to_user_id == user_id,
            Movement.reason == "issue",
            Movement.confirmed_at.is_(None),
        )
    )).scalars().all()

    from app.services.inventory.movements import confirm

    return [await confirm(db, m, actor_user_id=user_id) for m in pending]


async def return_session_kits(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    to_location_id: uuid.UUID,
) -> list[Movement]:
    """Kits come back. Ops names where they physically ended up — a return
    without a destination leaves the register saying a kit is on a shelf
    without saying which."""
    kits = (await db.execute(
        select(Kit).join(SessionKit, SessionKit.kit_id == Kit.id)
        .where(SessionKit.session_id == session_id, Kit.current_holder_user_id.isnot(None))
        .order_by(Kit.label)
    )).scalars().all()

    return [
        await move(
            db,
            actor_user_id=actor_user_id,
            reason="return",
            kit_id=kit.id,
            from_user_id=kit.current_holder_user_id,
            to_location_id=to_location_id,
            session_id=session_id,
        )
        for kit in kits
    ]


# ── merchandise ─────────────────────────────────────────────────────────────

async def issue_merch(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    item_id: uuid.UUID,
    to_user_id: uuid.UUID,
    from_location_id: uuid.UUID,
    qty: int = 1,
    returnable: bool | None = None,
    due_back_on: date | None = None,
    note: str | None = None,
) -> Movement:
    """Give someone a vest, a jacket or a T-shirt.

    `returnable` defaults to the item's own setting so ops isn't answering the
    same question fifty times, but stays overridable per issue. A due date is
    only meaningful on something expected back — putting one on a T-shirt
    nobody will return fills the overdue list with noise and stops it working
    for kits, which is what it is actually for.
    """
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(404, detail="Item not found")

    if returnable is None:
        returnable = item.returnable_default
    if not returnable:
        due_back_on = None

    return await move(
        db,
        actor_user_id=actor_user_id,
        reason="issue",
        item_id=item_id,
        qty=qty,
        from_location_id=from_location_id,
        to_user_id=to_user_id,
        due_back_on=due_back_on,
        note=note,
    )


async def held_by_user(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """What bulk items this person currently holds.

    Derived from the ledger rather than a denormalised column: issue and
    return quantities net out. Kits keep a denormalised holder because kit
    lists read it constantly; bulk holdings are rare enough to compute, and
    one fewer thing to keep honest.
    """
    out = (await db.execute(
        select(Movement, Item)
        .join(Item, Item.id == Movement.item_id)
        .where(Movement.to_user_id == user_id, Movement.item_id.isnot(None))
    )).all()
    back = (await db.execute(
        select(Movement).where(Movement.from_user_id == user_id, Movement.item_id.isnot(None))
    )).scalars().all()

    net: dict[uuid.UUID, dict] = {}
    for movement, item in out:
        entry = net.setdefault(item.id, {
            "item_id": item.id, "item_name": item.name, "qty": 0, "due_back_on": None,
        })
        entry["qty"] += movement.qty or 0
        if movement.due_back_on and (
            entry["due_back_on"] is None or movement.due_back_on < entry["due_back_on"]
        ):
            entry["due_back_on"] = movement.due_back_on

    for movement in back:
        entry = net.get(movement.item_id)
        if entry:
            entry["qty"] -= movement.qty or 0

    return [e for e in net.values() if e["qty"] > 0]


async def return_merch(
    db: AsyncSession,
    *,
    actor_user_id: uuid.UUID,
    item_id: uuid.UUID,
    from_user_id: uuid.UUID,
    to_location_id: uuid.UUID,
    qty: int = 1,
) -> Movement:
    held = {h["item_id"]: h["qty"] for h in await held_by_user(db, from_user_id)}
    if held.get(item_id, 0) < qty:
        raise HTTPException(
            409, detail=f"They only have {held.get(item_id, 0)} of those to give back"
        )

    return await move(
        db,
        actor_user_id=actor_user_id,
        reason="return",
        item_id=item_id,
        qty=qty,
        from_user_id=from_user_id,
        to_location_id=to_location_id,
    )


async def unconfirmed_handovers(db: AsyncSession) -> list[tuple[Movement, str | None]]:
    """Marked out, never acknowledged. The first of the two gaps worth seeing —
    it usually means the kit is sitting in an office nobody collected it from."""
    rows = (await db.execute(
        select(Movement, User.full_name)
        .outerjoin(User, User.id == Movement.to_user_id)
        .where(
            Movement.reason == "issue",
            Movement.to_user_id.isnot(None),
            Movement.confirmed_at.is_(None),
        )
        .order_by(Movement.created_at)
    )).all()
    return [(m, name) for m, name in rows]
