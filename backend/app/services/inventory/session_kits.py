"""Receiving and returning session kits — no custody leg, but a real hold.

Kits are assigned to a session and that is the whole story until the
instructor says otherwise. There is no "ops hands it out" step — but once an
instructor says "I'll bring this back later", they really do have it: the
kit's holder is set, same as any other kit someone is holding, so it shows up
on their own holdings page like anything else they're carrying. Saying
"returned" instead moves it straight to the session's warehouse — no ops
button, no location picker, because there's nothing left to decide once the
instructor has said where they are.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.kit import Kit
from app.models.inventory.session_kit import SessionKit
from app.models.sessions.session import Session
from app.services.inventory.cohort_kits import materialize_session_kits
from app.services.inventory.equipment import pickup_warehouse
from app.services.inventory.movements import move

RETURN_STATUSES = {"returned", "return_later"}


async def _session_kits(
    db: AsyncSession, *, session_id: uuid.UUID, kit_ids: list[uuid.UUID]
) -> list[SessionKit]:
    rows = (await db.execute(
        select(SessionKit).where(
            SessionKit.session_id == session_id, SessionKit.kit_id.in_(kit_ids)
        )
    )).scalars().all()
    if len(rows) != len(set(kit_ids)):
        raise HTTPException(404, detail="Some of those kits aren't assigned to this session")
    return rows


async def mark_kits_received(
    db: AsyncSession, *, session_id: uuid.UUID, kit_ids: list[uuid.UUID], actor_user_id: uuid.UUID
) -> list[SessionKit]:
    """The instructor confirms they have these kits. Per kit, and in bulk —
    select-all and one tap is the common case."""
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(404, detail="Session not found")
    # A kit the instructor has only ever inherited from the cohort default
    # has no row here yet — materialize first so "receive" has something to
    # mark (Phase 3 follow-up). No-op once this session has its own kits.
    await materialize_session_kits(db, session=session, actor_user_id=actor_user_id)

    rows = await _session_kits(db, session_id=session_id, kit_ids=kit_ids)
    now = datetime.now(timezone.utc)
    for row in rows:
        row.received_at = now
        row.received_by = actor_user_id
    await db.flush()
    return rows


async def mark_kits_returned(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    kit_ids: list[uuid.UUID],
    actor_user_id: uuid.UUID,
    later: bool = False,
    note: str | None = None,
) -> list[SessionKit]:
    """The instructor reports these kits back — or says they're coming back
    later.

    "Later" is a real hold: an issue movement to the instructor, so the kit
    shows up wherever else "what am I holding" is answered. "Returned" is a
    real move too, straight to the session's warehouse — no location to pick,
    since the session already has one. Changeable either way right up until
    the session is marked done: reporting "returned" and then "actually
    later" just moves the kit back out again, and vice versa."""
    session = await db.get(Session, session_id)
    if session is not None:
        # Same materialize-on-first-touch as `mark_kits_received` — a kit
        # reported back may only ever have been inherited, never assigned
        # directly to this session.
        await materialize_session_kits(db, session=session, actor_user_id=actor_user_id)
    rows = await _session_kits(db, session_id=session_id, kit_ids=kit_ids)
    now = datetime.now(timezone.utc)
    for row in rows:
        kit = await db.get(Kit, row.kit_id)
        if later:
            if kit.current_holder_user_id != actor_user_id:
                await move(
                    db, actor_user_id=actor_user_id, reason="issue", kit_id=kit.id,
                    from_warehouse_id=kit.current_warehouse_id, to_user_id=actor_user_id,
                    session_id=session_id,
                )
        elif kit.current_holder_user_id is not None:
            warehouse = await pickup_warehouse(db, session_id)
            await move(
                db, actor_user_id=actor_user_id, reason="return", kit_id=kit.id,
                from_user_id=kit.current_holder_user_id,
                to_warehouse_id=warehouse.id if warehouse else kit.current_warehouse_id,
                session_id=session_id,
            )
        row.return_status = "return_later" if later else "returned"
        row.returned_at = now
        row.returned_by = actor_user_id
        row.return_note = note
    await db.flush()
    return rows


async def confirm_kit_returns(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    kit_ids: list[uuid.UUID],
    actor_user_id: uuid.UUID,
    restock_warehouse_id: uuid.UUID | None = None,
) -> list[SessionKit]:
    """Ops reviews the instructor's report and closes it out. Restocking is
    optional and separate — a kit that never physically left its shelf has
    nothing to move, and this is the one place that distinction matters."""
    rows = await _session_kits(db, session_id=session_id, kit_ids=kit_ids)
    now = datetime.now(timezone.utc)
    for row in rows:
        if row.return_status is None:
            raise HTTPException(409, detail="That kit hasn't been reported back yet")
        row.ops_confirmed_at = now
        row.ops_confirmed_by = actor_user_id
        if restock_warehouse_id is not None:
            kit = await db.get(Kit, row.kit_id)
            if kit.current_warehouse_id != restock_warehouse_id:
                await move(
                    db,
                    actor_user_id=actor_user_id,
                    reason="transfer",
                    kit_id=kit.id,
                    from_warehouse_id=kit.current_warehouse_id,
                    to_warehouse_id=restock_warehouse_id,
                    session_id=session_id,
                )
    await db.flush()
    return rows
