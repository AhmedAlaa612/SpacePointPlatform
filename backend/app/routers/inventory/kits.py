"""Kits — list, detail, create (including bulk), move, and an instructor's own
kits (I1-3).

Ops actions are `require_operations`. `/inventory/my-kits` is
`require_session_delivery` (instructor|facilitator|operations), and an
instructor only ever sees kits they are actually holding — an unrelated kit
is a **404, not a 403**, matching this codebase's don't-leak-existence
convention (see services/sessions/delivery.py).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations, require_session_delivery
from app.db.session import get_db
from app.models.inventory.item import Item
from app.models.inventory.kit import Kit, KitItem
from app.models.inventory.kit_template import KitTemplate, KitTemplateItem
from app.models.inventory.location import Location
from app.models.inventory.movement import Movement
from app.models.user import User
from app.schemas.inventory.kits import (
    KitBulkCreate,
    KitContentOut,
    KitCreate,
    KitDetailOut,
    KitListItem,
    KitMoveIn,
    KitShortageOut,
    KitUpdate,
    MovementOut,
    MyKitOut,
)
from app.services.inventory import kit_shortages, move, shortages_for_kits

router = APIRouter(prefix="/inventory", tags=["inventory-kits"])


def _token() -> str:
    """QR payload: random, never derived from the label. A guessable code on a
    box is the same mistake as a guessable ticket id."""
    return uuid.uuid4().hex + uuid.uuid4().hex  # 64 chars


async def _names(db: AsyncSession, kits: list[Kit]) -> tuple[dict, dict, dict]:
    location_ids = {k.current_location_id for k in kits}
    holder_ids = {k.current_holder_user_id for k in kits if k.current_holder_user_id}
    template_ids = {k.template_id for k in kits}

    locations = dict((await db.execute(
        select(Location.id, Location.name).where(Location.id.in_(location_ids))
    )).all()) if location_ids else {}
    holders = dict((await db.execute(
        select(User.id, User.full_name).where(User.id.in_(holder_ids))
    )).all()) if holder_ids else {}
    templates = dict((await db.execute(
        select(KitTemplate.id, KitTemplate.code).where(KitTemplate.id.in_(template_ids))
    )).all()) if template_ids else {}
    return locations, holders, templates


@router.get("/kits", response_model=list[KitListItem])
async def list_kits(
    location_id: uuid.UUID | None = None,
    holder_user_id: uuid.UUID | None = None,
    template_id: uuid.UUID | None = None,
    kit_status: str | None = Query(default=None, alias="status"),
    out_only: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    stmt = select(Kit).order_by(Kit.label)
    if location_id:
        stmt = stmt.where(Kit.current_location_id == location_id)
    if holder_user_id:
        stmt = stmt.where(Kit.current_holder_user_id == holder_user_id)
    if template_id:
        stmt = stmt.where(Kit.template_id == template_id)
    if kit_status:
        stmt = stmt.where(Kit.status == kit_status)
    if out_only:
        stmt = stmt.where(Kit.current_holder_user_id.isnot(None))

    kits = (await db.execute(stmt)).scalars().all()
    if not kits:
        return []

    locations, holders, templates = await _names(db, kits)
    # One query for the whole page, never one per row.
    shortages = await shortages_for_kits(db, [k.id for k in kits])

    return [
        KitListItem(
            id=k.id, template_id=k.template_id, label=k.label, status=k.status,
            current_location_id=k.current_location_id,
            current_holder_user_id=k.current_holder_user_id,
            notes=k.notes,
            template_code=templates.get(k.template_id, ""),
            location_name=locations.get(k.current_location_id, ""),
            holder_name=holders.get(k.current_holder_user_id),
            shortage_count=shortages.get(k.id, 0),
        )
        for k in kits
    ]


@router.post("/kits", response_model=KitDetailOut, status_code=status.HTTP_201_CREATED)
async def create_kit(
    body: KitCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    if await db.get(KitTemplate, body.template_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown template")
    if await db.get(Location, body.current_location_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown location")

    clash = (await db.execute(select(Kit.id).where(Kit.label == body.label))).first()
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A kit with this label already exists")

    kit = Kit(id=uuid.uuid4(), public_token=_token(), **body.model_dump())
    db.add(kit)
    await db.commit()
    return await get_kit(kit.id, db, _)


@router.post("/kits/bulk", response_model=list[KitListItem], status_code=status.HTTP_201_CREATED)
async def bulk_create_kits(
    body: KitBulkCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """Create N kits of one template at one location.

    This is the first-day path: entering an existing fleet one 28-field form
    at a time stalls halfway, and a half-entered register is worse than none.
    Labels continue from the highest existing number for that template's code,
    so running it twice doesn't collide.
    """
    template = await db.get(KitTemplate, body.template_id)
    if template is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown template")
    if await db.get(Location, body.location_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Unknown location")

    prefix = f"SP-{template.code}-"
    existing = (await db.execute(
        select(Kit.label).where(Kit.label.like(f"{prefix}%"))
    )).scalars().all()
    highest = 0
    for label in existing:
        tail = label[len(prefix):]
        if tail.isdigit():
            highest = max(highest, int(tail))

    bom = (await db.execute(
        select(KitTemplateItem.item_id, KitTemplateItem.required_qty)
        .where(KitTemplateItem.template_id == body.template_id)
    )).all() if body.complete else []

    created: list[Kit] = []
    for offset in range(1, body.count + 1):
        kit = Kit(
            id=uuid.uuid4(),
            template_id=body.template_id,
            label=f"{prefix}{highest + offset:04d}",
            public_token=_token(),
            current_location_id=body.location_id,
        )
        db.add(kit)
        created.append(kit)
        for item_id, qty in bom:
            db.add(KitItem(id=uuid.uuid4(), kit_id=kit.id, item_id=item_id, qty=qty))

    await db.commit()

    locations, holders, templates = await _names(db, created)
    shortages = await shortages_for_kits(db, [k.id for k in created])
    return [
        KitListItem(
            id=k.id, template_id=k.template_id, label=k.label, status=k.status,
            current_location_id=k.current_location_id,
            current_holder_user_id=None, notes=None,
            template_code=templates.get(k.template_id, ""),
            location_name=locations.get(k.current_location_id, ""),
            holder_name=None,
            shortage_count=shortages.get(k.id, 0),
        )
        for k in created
    ]


@router.get("/kits/{kit_id}", response_model=KitDetailOut)
async def get_kit(
    kit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    kit = await db.get(Kit, kit_id)
    if kit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kit not found")

    template = await db.get(KitTemplate, kit.template_id)
    location = await db.get(Location, kit.current_location_id)
    holder = await db.get(User, kit.current_holder_user_id) if kit.current_holder_user_id else None

    contents = (await db.execute(
        select(KitItem, Item).join(Item, Item.id == KitItem.item_id)
        .where(KitItem.kit_id == kit_id).order_by(Item.category, Item.name)
    )).all()

    return KitDetailOut(
        id=kit.id, template_id=kit.template_id, label=kit.label, status=kit.status,
        current_location_id=kit.current_location_id,
        current_holder_user_id=kit.current_holder_user_id,
        notes=kit.notes, public_token=kit.public_token,
        template_code=template.code if template else "",
        template_name=template.name if template else "",
        location_name=location.name if location else "",
        holder_name=holder.full_name if holder else None,
        contents=[
            KitContentOut(item_id=item.id, item_name=item.name, qty=ki.qty)
            for ki, item in contents
        ],
        shortages=[KitShortageOut(**s) for s in await kit_shortages(db, kit)],
    )


@router.patch("/kits/{kit_id}", response_model=KitDetailOut)
async def update_kit(
    kit_id: uuid.UUID,
    body: KitUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    kit = await db.get(Kit, kit_id)
    if kit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kit not found")

    changes = body.model_dump(exclude_unset=True)
    if "label" in changes and changes["label"] != kit.label:
        clash = (await db.execute(select(Kit.id).where(Kit.label == changes["label"]))).first()
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="A kit with this label already exists")

    for field, value in changes.items():
        setattr(kit, field, value)
    await db.commit()
    return await get_kit(kit_id, db, _)


@router.post("/kits/{kit_id}/move", response_model=MovementOut, status_code=status.HTTP_201_CREATED)
async def move_kit(
    kit_id: uuid.UUID,
    body: KitMoveIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    kit = await db.get(Kit, kit_id)
    if kit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kit not found")

    movement = await move(
        db,
        actor_user_id=current_user.id,
        reason=body.reason,
        kit_id=kit_id,
        from_location_id=kit.current_location_id if body.to_user_id else None,
        from_user_id=kit.current_holder_user_id if body.to_location_id else None,
        to_location_id=body.to_location_id,
        to_user_id=body.to_user_id,
        session_id=body.session_id,
        due_back_on=body.due_back_on,
        note=body.note,
    )
    await db.commit()
    await db.refresh(movement)
    return movement


@router.get("/kits/{kit_id}/movements", response_model=list[MovementOut])
async def kit_history(
    kit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """Everything that ever happened to this kit — where it went, and what
    went into or out of it."""
    if await db.get(Kit, kit_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Kit not found")

    return (await db.execute(
        select(Movement)
        .where(
            (Movement.kit_id == kit_id)
            | (Movement.to_kit_id == kit_id)
            | (Movement.from_kit_id == kit_id)
        )
        .order_by(Movement.created_at.desc())
    )).scalars().all()


# ── instructor-facing ───────────────────────────────────────────────────────

@router.get("/my-kits", response_model=list[MyKitOut])
async def my_kits(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Kits this person is currently holding. Reads the denormalised holder
    column rather than replaying the ledger — that is what it is for."""
    kits = (await db.execute(
        select(Kit).where(Kit.current_holder_user_id == current_user.id).order_by(Kit.label)
    )).scalars().all()
    if not kits:
        return []

    locations, _holders, _templates = await _names(db, kits)
    template_names = dict((await db.execute(
        select(KitTemplate.id, KitTemplate.name)
        .where(KitTemplate.id.in_({k.template_id for k in kits}))
    )).all())
    shortages = await shortages_for_kits(db, [k.id for k in kits])

    # The open issue movement carries the deadline, if there is one.
    due = dict((await db.execute(
        select(Movement.kit_id, Movement.due_back_on).where(
            Movement.kit_id.in_([k.id for k in kits]),
            Movement.to_user_id == current_user.id,
            Movement.due_back_on.isnot(None),
        ).order_by(Movement.created_at.desc())
    )).all())

    return [
        MyKitOut(
            id=k.id, label=k.label,
            template_name=template_names.get(k.template_id, ""),
            status=k.status,
            location_name=locations.get(k.current_location_id, ""),
            due_back_on=due.get(k.id),
            shortage_count=shortages.get(k.id, 0),
        )
        for k in kits
    ]
