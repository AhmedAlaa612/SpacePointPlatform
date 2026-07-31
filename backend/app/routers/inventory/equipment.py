"""Equipment pickup endpoints (I2-7).

    GET  /inventory/sessions/{id}/equipment          what I took, and from where
    GET  /inventory/sessions/{id}/equipment/search   the shelf at the pickup point (B3)
    POST /inventory/sessions/{id}/equipment/take     "I also took these"
    POST /inventory/sessions/{id}/equipment/return   "I brought these back"

All four are `require_session_delivery` and go through
`_get_deliverable_session`, the same gate the rest of the delivery flow uses —
so an instructor can only record equipment against a session they are actually
teaching, and an unrelated session is a 404 rather than a 403.

The instructor is recording their *own* pickup, so the actor is both the person
doing it and the person receiving. Ops never has to be in the room, which is
the whole point: today this happens over WhatsApp and never reaches a system.
"""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_session_delivery
from app.db.session import get_db
from app.models.user import User
from app.schemas.inventory.equipment import (
    EquipmentSearchOut,
    ReturnEquipmentIn,
    SessionEquipmentOut,
    TakeEquipmentIn,
    TakenEquipmentOut,
)
from app.schemas.inventory.kits import MovementOut
from app.services.inventory import (
    pickup_location,
    return_equipment,
    search_equipment,
    session_equipment,
    take_equipment,
)
from app.services.sessions.delivery import _get_deliverable_session

router = APIRouter(prefix="/inventory", tags=["inventory-equipment"])


async def _view(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID) -> SessionEquipmentOut:
    location = await pickup_location(db, session_id)
    lines = await session_equipment(db, session_id=session_id, user_id=user_id)
    return SessionEquipmentOut(
        location_id=location.id if location else None,
        location_name=location.name if location else None,
        lines=[TakenEquipmentOut(**line) for line in lines],
        outstanding_count=sum(1 for line in lines if line["outstanding"] > 0),
    )


@router.get("/sessions/{session_id}/equipment", response_model=SessionEquipmentOut)
async def get_session_equipment(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Equipment this instructor took for this session, and the collection
    point derived from the assigned kits."""
    await _get_deliverable_session(db, session_id, current_user)
    return await _view(db, session_id, current_user.id)


@router.get("/sessions/{session_id}/equipment/search", response_model=list[EquipmentSearchOut])
async def search_session_equipment(
    session_id: uuid.UUID,
    q: str = Query(default="", description="Optional free-text filter; empty returns the whole shelf"),
    location_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """The collection point's shelf (B3) — everything in stock there, in
    one tick-list, optionally narrowed by name."""
    await _get_deliverable_session(db, session_id, current_user)

    if location_id is None:
        location = await pickup_location(db, session_id)
        if location is None:
            return []
        location_id = location.id

    return [
        EquipmentSearchOut(**row)
        for row in await search_equipment(db, location_id=location_id, q=q)
    ]


@router.post(
    "/sessions/{session_id}/equipment/take",
    response_model=list[MovementOut],
    status_code=status.HTTP_201_CREATED,
)
async def take_session_equipment(
    session_id: uuid.UUID,
    body: TakeEquipmentIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Record non-kit equipment collected for this session."""
    await _get_deliverable_session(db, session_id, current_user)
    movements = await take_equipment(
        db,
        session_id=session_id,
        actor_user_id=current_user.id,
        lines=[(line.item_id, line.qty) for line in body.lines],
        location_id=body.location_id,
        note=body.note,
    )
    await db.commit()
    return movements


@router.post(
    "/sessions/{session_id}/equipment/return",
    response_model=list[MovementOut],
    status_code=status.HTTP_201_CREATED,
)
async def return_session_equipment(
    session_id: uuid.UUID,
    body: ReturnEquipmentIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Give equipment back. Lines left out stay outstanding — that is how
    "returning later" is recorded, because it is what actually happened."""
    await _get_deliverable_session(db, session_id, current_user)
    movements = await return_equipment(
        db,
        session_id=session_id,
        actor_user_id=current_user.id,
        lines=[(line.item_id, line.qty) for line in body.lines],
        to_location_id=body.to_location_id,
    )
    await db.commit()
    return movements
