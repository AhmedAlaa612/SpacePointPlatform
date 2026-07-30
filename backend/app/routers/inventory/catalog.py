"""Locations, item catalogue and kit templates (I1-3).

Straightforward CRUD, so it lives in the router rather than a service module —
matching routers/sessions/programs.py. Everything here is `require_operations`
(admin passes automatically): the storekeeper restocks, they don't redefine
what a kit is.

**One exception: `GET /locations` is `require_storekeeper`.** Naming a
warehouse is a precondition of every job a storekeeper has — recording a
count, fulfilling a kit, receiving goods — so withholding the list of
warehouses made all three unusable while leaving the writes correctly shut.
Creating and editing locations remain `require_operations`.

No `/api` prefix — nginx strips it before the app sees the request.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations, require_storekeeper
from app.db.session import get_db
from app.models.inventory.item import Item
from app.models.inventory.kit import Kit, KitItem
from app.models.inventory.kit_template import KitTemplate, KitTemplateItem
from app.models.inventory.location import Location
from app.models.inventory.stock import StockLevel
from app.models.user import User
from app.schemas.inventory.catalog import (
    ItemCreate,
    ItemOut,
    ItemUpdate,
    LocationCreate,
    LocationOut,
    LocationUpdate,
    TemplateCreate,
    TemplateDetailOut,
    TemplateLineIn,
    TemplateLineOut,
    TemplateOut,
    TemplateUpdate,
)

router = APIRouter(prefix="/inventory", tags=["inventory-catalog"])


# ── locations ───────────────────────────────────────────────────────────────

@router.get("/locations", response_model=list[LocationOut])
async def list_locations(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    # Read-only, and `require_storekeeper` admits storekeeper *or* operations.
    # Every write below stays `require_operations`. A storekeeper cannot record
    # a count, fulfil a kit or receive goods without naming a warehouse, so
    # withholding the *list* of warehouses made all three unusable.
    _: User = Depends(require_storekeeper),
):
    stmt = select(Location).order_by(Location.country, Location.name)
    if not include_inactive:
        stmt = stmt.where(Location.is_active.is_(True))
    return (await db.execute(stmt)).scalars().all()


@router.post("/locations", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
async def create_location(
    body: LocationCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    location = Location(id=uuid.uuid4(), **body.model_dump())
    location.country = location.country.upper()
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return location


@router.patch("/locations/{location_id}", response_model=LocationOut)
async def update_location(
    location_id: uuid.UUID,
    body: LocationUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    location = await db.get(Location, location_id)
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Location not found")

    changes = body.model_dump(exclude_unset=True)
    if "country" in changes and changes["country"]:
        changes["country"] = changes["country"].upper()

    if changes.get("is_active") is False:
        kits_here = await db.scalar(
            select(func.count()).select_from(Kit).where(Kit.current_location_id == location_id)
        )
        if kits_here:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=f"{kits_here} kit(s) still sit here — move them before deactivating.",
            )

    for field, value in changes.items():
        setattr(location, field, value)
    await db.commit()
    await db.refresh(location)
    return location


# ── items ───────────────────────────────────────────────────────────────────

@router.get("/items", response_model=list[ItemOut])
async def list_items(
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    stmt = select(Item).order_by(Item.category, Item.name)
    if category:
        stmt = stmt.where(Item.category == category)
    return (await db.execute(stmt)).scalars().all()


@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ItemCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    clash = (await db.execute(select(Item.id).where(func.lower(Item.name) == body.name.lower()))).first()
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An item with this name already exists")

    item = Item(id=uuid.uuid4(), **body.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.patch("/items/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: uuid.UUID,
    body: ItemUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")

    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"].lower() != item.name.lower():
        clash = (await db.execute(
            select(Item.id).where(func.lower(Item.name) == changes["name"].lower())
        )).first()
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="An item with this name already exists")

    for field, value in changes.items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """Only ever deletes an item nothing uses.

    The FKs are RESTRICT, so the database would refuse anyway — this exists to
    say *why* instead of surfacing an IntegrityError.
    """
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")

    in_kits = await db.scalar(select(func.count()).select_from(KitItem).where(KitItem.item_id == item_id))
    in_templates = await db.scalar(
        select(func.count()).select_from(KitTemplateItem).where(KitTemplateItem.item_id == item_id)
    )
    in_stock = await db.scalar(
        select(func.count()).select_from(StockLevel).where(StockLevel.item_id == item_id, StockLevel.qty > 0)
    )
    if in_kits or in_templates or in_stock:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"Still in use: {in_kits} kit(s), {in_templates} template line(s), "
                f"{in_stock} location(s) with stock."
            ),
        )

    await db.delete(item)
    await db.commit()


# ── kit templates ───────────────────────────────────────────────────────────

@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    return (await db.execute(select(KitTemplate).order_by(KitTemplate.code))).scalars().all()


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    code = body.code.upper()
    clash = (await db.execute(select(KitTemplate.id).where(KitTemplate.code == code))).first()
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A template with this code already exists")

    template = KitTemplate(id=uuid.uuid4(), name=body.name, code=code)
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


@router.get("/templates/{template_id}", response_model=TemplateDetailOut)
async def get_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    template = await db.get(KitTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template not found")

    lines = (await db.execute(
        select(KitTemplateItem, Item)
        .join(Item, Item.id == KitTemplateItem.item_id)
        .where(KitTemplateItem.template_id == template_id)
        .order_by(Item.category, Item.name)
    )).all()

    return TemplateDetailOut(
        id=template.id, name=template.name, code=template.code, is_active=template.is_active,
        items=[
            TemplateLineOut(
                item_id=item.id, item_name=item.name,
                required_qty=line.required_qty, is_consumable=item.is_consumable,
            )
            for line, item in lines
        ],
    )


@router.patch("/templates/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    template = await db.get(KitTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    await db.commit()
    await db.refresh(template)
    return template


@router.put("/templates/{template_id}/items", response_model=TemplateDetailOut)
async def set_template_items(
    template_id: uuid.UUID,
    body: list[TemplateLineIn],
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    """Replace the whole bill of materials in one call.

    Whole-list rather than per-line so the client never has to diff, and so a
    half-applied edit can't leave a template describing a kit that never
    existed. Editing the BOM does not touch any existing kit's contents —
    completeness is computed at read time, so the next check simply reports
    against the new list.
    """
    template = await db.get(KitTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template not found")

    seen: set[uuid.UUID] = set()
    for line in body:
        if line.item_id in seen:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="The same item is listed twice")
        seen.add(line.item_id)

    if seen:
        known = set((await db.execute(select(Item.id).where(Item.id.in_(seen)))).scalars().all())
        missing = seen - known
        if missing:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"{len(missing)} unknown item(s)")

    existing = (await db.execute(
        select(KitTemplateItem).where(KitTemplateItem.template_id == template_id)
    )).scalars().all()
    for line in existing:
        await db.delete(line)
    await db.flush()

    for line in body:
        db.add(KitTemplateItem(
            id=uuid.uuid4(), template_id=template_id,
            item_id=line.item_id, required_qty=line.required_qty,
        ))
    await db.commit()

    return await get_template(template_id, db, _)
