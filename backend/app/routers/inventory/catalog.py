"""Locations, item catalogue and kit templates (I1-3).

Straightforward CRUD, so it lives in the router rather than a service module —
matching routers/sessions/programs.py.

Every write here is `require_inventory_manage` (operations or coo; admin
passes automatically) — a storekeeper restocks, they don't redefine what a
kit is. Every read is `require_storekeeper` (storekeeper, operations, or
coo) — 2026-08-27: originally only `GET /locations` was open this way
("naming a warehouse is a precondition of every job a storekeeper has —
recording a count, fulfilling a kit, receiving goods"), but the same logic
turned out to apply to the whole catalogue: a storekeeper counting a kit
needs to see what's actually supposed to be in it, which means reading
`/items` and `/templates` too. Operator directive, same incident: "if I can
see a page with my role, I can use it" — no read a storekeeper's own pages
depend on can be walled off from them.

No `/api` prefix — nginx strips it before the app sees the request.
"""

import uuid

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import require_admin, require_inventory_manage, require_storekeeper
from app.db.session import get_db
from app.models.inventory.city import City
from app.models.inventory.equipment_flag import EquipmentReturnFlag
from app.models.inventory.item import Item
from app.models.inventory.item_category import ItemCategory
from app.models.inventory.item_subcategory import ItemSubcategory
from app.models.inventory.kit import Kit, KitItem
from app.models.inventory.kit_template import KitTemplate, KitTemplateItem
from app.models.inventory.location import Location
from app.models.inventory.movement import Movement
from app.models.inventory.warehouse import Warehouse
from app.models.inventory.warehouse_cabin import ItemCabinAssignment, WarehouseBox, WarehouseCabin
from app.models.inventory.stock import StockLevel
from app.models.user import User
from app.schemas.inventory.warehouse import (
    ItemCabinAssignmentIn,
    ItemCabinAssignmentOut,
    WarehouseBoxCreate,
    WarehouseBoxItemsIn,
    WarehouseBoxOut,
    WarehouseBoxUpdate,
    WarehouseCabinCreate,
    WarehouseCabinOut,
    WarehouseCabinUpdate,
    WarehouseCreate,
    WarehouseOut,
    WarehouseUpdate,
)
from app.schemas.inventory.catalog import (
    CityCreate,
    CityOut,
    CityUpdate,
    ItemCategoryCreate,
    ItemCategoryOut,
    ItemCategoryUpdate,
    ItemSubcategoryCreate,
    ItemSubcategoryOut,
    ItemSubcategoryUpdate,
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
from app.services import storage

router = APIRouter(prefix="/inventory", tags=["inventory-catalog"])

ITEM_IMAGES_BUCKET = "item-images"
ITEM_DATASHEETS_BUCKET = "item-datasheets"
CABIN_IMAGES_BUCKET = "cabin-images"
BOX_IMAGES_BUCKET = "box-images"


async def _item_out(item: Item) -> ItemOut:
    out = ItemOut.model_validate(item)
    out.image_url = (
        await storage.resolve_url(item.image_bucket, item.image_path)
        if item.image_bucket and item.image_path
        else None
    )
    out.datasheet_url = (
        await storage.resolve_url(item.datasheet_bucket, item.datasheet_path)
        if item.datasheet_bucket and item.datasheet_path
        else None
    )
    return out


# ── locations ───────────────────────────────────────────────────────────────

async def _location_out(db: AsyncSession, location: Location) -> LocationOut:
    """`LocationOut.city_name` and `LocationOut.country` are derived, not
    real columns — the canonical country of a location is its city's
    country. Every location-returning endpoint goes through this instead of
    `return location`, same reasoning as `_item_out`/`_cohort_out`
    elsewhere."""
    out = LocationOut.model_validate(location)
    if location.city_id:
        city = await db.get(City, location.city_id)
        if city:
            out.city_name = city.name
            out.country = city.country
    return out


@router.get("/locations", response_model=list[LocationOut])
async def list_locations(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    # Read-only, and `require_storekeeper` admits storekeeper, operations, or
    # coo. Every write below stays `require_inventory_manage`. A storekeeper cannot record
    # a count, fulfil a kit or receive goods without naming a warehouse, so
    # withholding the *list* of warehouses made all three unusable.
    _: User = Depends(require_storekeeper),
):
    stmt = select(Location).order_by(Location.country.asc().nullslast(), Location.name)
    if not include_inactive:
        stmt = stmt.where(Location.is_active.is_(True))
    rows = (await db.execute(stmt)).scalars().all()
    return [await _location_out(db, loc) for loc in rows]


@router.post("/locations", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
async def create_location(
    body: LocationCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    """No warehouse is created here (decoupled 2026-08-08, operator
    request) — a location is just a place; `POST /inventory/warehouses`
    is the only way a warehouse comes into existence, at ops's own
    initiative, whenever one is actually needed.

    2026-08-08: the city is the required anchor — a location is in a
    city, a city is in a country (matching `City.country` 1:1, so the
    legacy `country` column is always the city's code, uppercased)."""
    city = await db.get(City, body.city_id)
    if city is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="City not found")
    location = Location(id=uuid.uuid4(), **body.model_dump(), country=city.country)
    db.add(location)
    await db.commit()
    await db.refresh(location)
    return await _location_out(db, location)


@router.patch("/locations/{location_id}", response_model=LocationOut)
async def update_location(
    location_id: uuid.UUID,
    body: LocationUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    location = await db.get(Location, location_id)
    if location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Location not found")

    changes = body.model_dump(exclude_unset=True)
    # Moving a location to a different city re-derives the legacy country
    # column from that city — the country is never entered directly.
    if "city_id" in changes and changes.get("city_id") is not None:
        city = await db.get(City, changes["city_id"])
        if city is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="City not found")
        changes["country"] = city.country

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
    return await _location_out(db, location)


# ── cities ───────────────────────────────────────────────────────────────────

@router.get("/cities", response_model=list[CityOut])
async def list_cities(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_storekeeper),
):
    stmt = select(City).order_by(City.country, City.name)
    if not include_inactive:
        stmt = stmt.where(City.is_active.is_(True))
    return (await db.execute(stmt)).scalars().all()


@router.post("/cities", response_model=CityOut, status_code=status.HTTP_201_CREATED)
async def create_city(
    body: CityCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    city = City(id=uuid.uuid4(), **body.model_dump())
    city.country = city.country.upper()
    db.add(city)
    await db.commit()
    await db.refresh(city)
    return city


@router.patch("/cities/{city_id}", response_model=CityOut)
async def update_city(
    city_id: uuid.UUID,
    body: CityUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    city = await db.get(City, city_id)
    if city is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="City not found")

    changes = body.model_dump(exclude_unset=True)
    if "country" in changes and changes["country"]:
        changes["country"] = changes["country"].upper()
    for field, value in changes.items():
        setattr(city, field, value)
    await db.commit()
    await db.refresh(city)
    return city


# ── warehouses ──────────────────────────────────────────────────────────────

WAREHOUSE_IMAGES_BUCKET = "warehouse-images"


async def _warehouse_out(
    db: AsyncSession,
    wh: Warehouse,
    location_name: str | None = None,
    cabins: list[WarehouseCabinOut] | None = None,
) -> WarehouseOut:
    if location_name is None and wh.location_id:
        loc = await db.get(Location, wh.location_id)
        location_name = loc.name if loc else None

    image_url = None
    if wh.image_bucket and wh.image_path:
        image_url = await storage.resolve_url(wh.image_bucket, wh.image_path)

    if cabins is None:
        cabins_stmt = (
            select(
                WarehouseCabin,
                func.count(ItemCabinAssignment.id).label("item_count"),
            )
            .outerjoin(ItemCabinAssignment, ItemCabinAssignment.cabin_id == WarehouseCabin.id)
            .where(WarehouseCabin.warehouse_id == wh.id)
            .group_by(WarehouseCabin.id)
            .order_by(WarehouseCabin.sort_order, WarehouseCabin.name)
        )
        rows = (await db.execute(cabins_stmt)).all()
        cabins = [
            WarehouseCabinOut(
                id=c.id,
                warehouse_id=c.warehouse_id,
                name=c.name,
                description=c.description,
                pin_x=c.pin_x,
                pin_y=c.pin_y,
                sort_order=c.sort_order,
                item_count=count,
                created_at=c.created_at,
            )
            for c, count in rows
        ]

    return WarehouseOut(
        id=wh.id,
        location_id=wh.location_id,
        name=wh.name,
        code=wh.code,
        is_active=wh.is_active,
        address=wh.address,
        notes=wh.notes,
        created_at=wh.created_at,
        location_name=location_name,
        image_url=image_url,
        cabins=cabins,
    )


@router.get("/warehouses", response_model=list[WarehouseOut])
async def list_warehouses(
    location_id: uuid.UUID | None = None,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_storekeeper),
):
    stmt = (
        select(Warehouse, Location.name.label("location_name"))
        .join(Location, Warehouse.location_id == Location.id)
        .order_by(Location.name, Warehouse.name)
    )
    if location_id:
        stmt = stmt.where(Warehouse.location_id == location_id)
    if not include_inactive:
        stmt = stmt.where(Warehouse.is_active.is_(True))

    rows = (await db.execute(stmt)).all()
    if not rows:
        return []

    wh_ids = [wh.id for wh, _ in rows]
    cabins_stmt = (
        select(
            WarehouseCabin,
            func.count(ItemCabinAssignment.id).label("item_count"),
        )
        .outerjoin(ItemCabinAssignment, ItemCabinAssignment.cabin_id == WarehouseCabin.id)
        .where(WarehouseCabin.warehouse_id.in_(wh_ids))
        .group_by(WarehouseCabin.id)
        .order_by(WarehouseCabin.sort_order, WarehouseCabin.name)
    )
    cabin_rows = (await db.execute(cabins_stmt)).all()
    cabins_by_wh: dict[uuid.UUID, list[WarehouseCabinOut]] = {wid: [] for wid in wh_ids}
    for c, count in cabin_rows:
        cabins_by_wh[c.warehouse_id].append(
            WarehouseCabinOut(
                id=c.id,
                warehouse_id=c.warehouse_id,
                name=c.name,
                description=c.description,
                pin_x=c.pin_x,
                pin_y=c.pin_y,
                sort_order=c.sort_order,
                item_count=count,
                created_at=c.created_at,
            )
        )

    return [
        await _warehouse_out(db, wh, loc_name, cabins=cabins_by_wh.get(wh.id, []))
        for wh, loc_name in rows
    ]


@router.post("/warehouses", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    body: WarehouseCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    location = await db.get(Location, body.location_id)
    if not location:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Parent location not found")

    wh = Warehouse(id=uuid.uuid4(), **body.model_dump())
    db.add(wh)
    await db.commit()
    await db.refresh(wh)

    return await _warehouse_out(db, wh, location.name)


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseOut)
async def update_warehouse(
    warehouse_id: uuid.UUID,
    body: WarehouseUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    wh = await db.get(Warehouse, warehouse_id)
    if not wh:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")

    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(wh, k, v)

    await db.commit()
    await db.refresh(wh)

    location = await db.get(Location, wh.location_id)
    return await _warehouse_out(db, wh, location.name if location else None)


@router.put("/warehouses/{warehouse_id}/image", response_model=WarehouseOut)
async def set_warehouse_image(
    warehouse_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    wh = await db.get(Warehouse, warehouse_id)
    if not wh:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")

    path = f"wh_{uuid.uuid4().hex}_{file.filename or 'warehouse.jpg'}"
    await storage.upload_to_path(
        WAREHOUSE_IMAGES_BUCKET, path, await file.read(), file.content_type or "image/jpeg"
    )
    wh.image_bucket = WAREHOUSE_IMAGES_BUCKET
    wh.image_path = path
    await db.commit()
    await db.refresh(wh)
    return await _warehouse_out(db, wh)


@router.delete("/warehouses/{warehouse_id}/image", response_model=WarehouseOut)
async def remove_warehouse_image(
    warehouse_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    wh = await db.get(Warehouse, warehouse_id)
    if not wh:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")

    wh.image_bucket = None
    wh.image_path = None
    await db.commit()
    await db.refresh(wh)
    return await _warehouse_out(db, wh)


# ── warehouse cabins ───────────────────────────────────────────────────────

async def _cabin_out(db: AsyncSession, c: WarehouseCabin, count: int = 0) -> WarehouseCabinOut:
    img_url = None
    if c.image_bucket and c.image_path:
        img_url = await storage.resolve_url(c.image_bucket, c.image_path)

    # Load boxes for this cabin
    boxes_stmt = (
        select(
            WarehouseBox,
            func.count(ItemCabinAssignment.id).label("item_count"),
        )
        .outerjoin(ItemCabinAssignment, ItemCabinAssignment.box_id == WarehouseBox.id)
        .where(WarehouseBox.cabin_id == c.id)
        .group_by(WarehouseBox.id)
        .order_by(WarehouseBox.sort_order, WarehouseBox.name)
    )
    b_rows = (await db.execute(boxes_stmt)).all()
    boxes_out = []
    for b, b_count in b_rows:
        b_img = None
        if b.image_bucket and b.image_path:
            b_img = await storage.resolve_url(b.image_bucket, b.image_path)
        item_ids = (await db.execute(
            select(ItemCabinAssignment.item_id).where(ItemCabinAssignment.box_id == b.id)
        )).scalars().all()
        boxes_out.append(
            WarehouseBoxOut(
                id=b.id,
                warehouse_id=b.warehouse_id,
                cabin_id=b.cabin_id,
                cabin_name=c.name,
                name=b.name,
                description=b.description,
                image_url=b_img,
                sort_order=b.sort_order,
                item_count=b_count or 0,
                item_ids=list(item_ids),
                created_at=b.created_at,
            )
        )

    return WarehouseCabinOut(
        id=c.id,
        warehouse_id=c.warehouse_id,
        name=c.name,
        description=c.description,
        pin_x=c.pin_x,
        pin_y=c.pin_y,
        sort_order=c.sort_order,
        image_url=img_url,
        box_count=len(boxes_out),
        boxes=boxes_out,
        item_count=count,
        created_at=c.created_at,
    )


@router.get("/warehouses/{warehouse_id}/cabins", response_model=list[WarehouseCabinOut])
async def list_warehouse_cabins(
    warehouse_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_storekeeper),
):
    wh = await db.get(Warehouse, warehouse_id)
    if not wh:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")
    stmt = (
        select(
            WarehouseCabin,
            func.count(ItemCabinAssignment.id).label("item_count"),
        )
        .outerjoin(ItemCabinAssignment, ItemCabinAssignment.cabin_id == WarehouseCabin.id)
        .where(WarehouseCabin.warehouse_id == warehouse_id)
        .group_by(WarehouseCabin.id)
        .order_by(WarehouseCabin.sort_order, WarehouseCabin.name)
    )
    rows = (await db.execute(stmt)).all()
    return [await _cabin_out(db, c, count) for c, count in rows]


@router.post("/warehouses/{warehouse_id}/cabins", response_model=WarehouseCabinOut, status_code=status.HTTP_201_CREATED)
async def create_warehouse_cabin(
    warehouse_id: uuid.UUID,
    body: WarehouseCabinCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    wh = await db.get(Warehouse, warehouse_id)
    if not wh:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")
    name = body.name.strip()
    clash = (await db.execute(
        select(WarehouseCabin.id).where(
            WarehouseCabin.warehouse_id == warehouse_id,
            func.lower(WarehouseCabin.name) == name.lower(),
        )
    )).first()
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A cabin with this name already exists in this warehouse")

    top = await db.scalar(
        select(func.max(WarehouseCabin.sort_order)).where(WarehouseCabin.warehouse_id == warehouse_id)
    )
    cabin = WarehouseCabin(
        id=uuid.uuid4(),
        warehouse_id=warehouse_id,
        name=name,
        description=body.description,
        pin_x=body.pin_x,
        pin_y=body.pin_y,
        sort_order=body.sort_order if body.sort_order != 0 else ((top or 0) + 1),
    )
    db.add(cabin)
    await db.commit()
    await db.refresh(cabin)
    return await _cabin_out(db, cabin, 0)


@router.patch("/warehouses/{warehouse_id}/cabins/{cabin_id}", response_model=WarehouseCabinOut)
async def update_warehouse_cabin(
    warehouse_id: uuid.UUID,
    cabin_id: uuid.UUID,
    body: WarehouseCabinUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    cabin = await db.get(WarehouseCabin, cabin_id)
    if not cabin or cabin.warehouse_id != warehouse_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cabin not found")

    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"]:
        new_name = changes["name"].strip()
        if new_name.lower() != cabin.name.lower():
            clash = (await db.execute(
                select(WarehouseCabin.id).where(
                    WarehouseCabin.warehouse_id == warehouse_id,
                    func.lower(WarehouseCabin.name) == new_name.lower(),
                )
            )).first()
            if clash:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="A cabin with this name already exists in this warehouse")
        changes["name"] = new_name

    for k, v in changes.items():
        setattr(cabin, k, v)

    await db.commit()
    await db.refresh(cabin)

    count = await db.scalar(
        select(func.count(ItemCabinAssignment.id)).where(ItemCabinAssignment.cabin_id == cabin_id)
    )
    return await _cabin_out(db, cabin, count or 0)


@router.delete("/warehouses/{warehouse_id}/cabins/{cabin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_warehouse_cabin(
    warehouse_id: uuid.UUID,
    cabin_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    cabin = await db.get(WarehouseCabin, cabin_id)
    if not cabin or cabin.warehouse_id != warehouse_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cabin not found")

    await db.delete(cabin)
    await db.commit()


@router.put("/warehouses/{warehouse_id}/cabins/{cabin_id}/image", response_model=WarehouseCabinOut)
async def set_cabin_image(
    warehouse_id: uuid.UUID,
    cabin_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    cabin = await db.get(WarehouseCabin, cabin_id)
    if not cabin or cabin.warehouse_id != warehouse_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cabin not found")

    path = f"cabin_{uuid.uuid4().hex}_{file.filename or 'cabin.jpg'}"
    await storage.upload_to_path(
        CABIN_IMAGES_BUCKET, path, await file.read(), file.content_type or "image/jpeg"
    )
    cabin.image_bucket = CABIN_IMAGES_BUCKET
    cabin.image_path = path
    await db.commit()
    await db.refresh(cabin)
    count = await db.scalar(
        select(func.count(ItemCabinAssignment.id)).where(ItemCabinAssignment.cabin_id == cabin_id)
    )
    return await _cabin_out(db, cabin, count or 0)


@router.delete("/warehouses/{warehouse_id}/cabins/{cabin_id}/image", response_model=WarehouseCabinOut)
async def remove_cabin_image(
    warehouse_id: uuid.UUID,
    cabin_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    cabin = await db.get(WarehouseCabin, cabin_id)
    if not cabin or cabin.warehouse_id != warehouse_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cabin not found")

    cabin.image_bucket = None
    cabin.image_path = None
    await db.commit()
    await db.refresh(cabin)
    count = await db.scalar(
        select(func.count(ItemCabinAssignment.id)).where(ItemCabinAssignment.cabin_id == cabin_id)
    )
    return await _cabin_out(db, cabin, count or 0)


# ── warehouse boxes ─────────────────────────────────────────────────────────

async def _box_out(db: AsyncSession, box: WarehouseBox, cabin_name: str | None = None, count: int = 0) -> WarehouseBoxOut:
    if cabin_name is None:
        cabin = await db.get(WarehouseCabin, box.cabin_id)
        cabin_name = cabin.name if cabin else None

    img_url = None
    if box.image_bucket and box.image_path:
        img_url = await storage.resolve_url(box.image_bucket, box.image_path)

    item_ids = (await db.execute(
        select(ItemCabinAssignment.item_id).where(ItemCabinAssignment.box_id == box.id)
    )).scalars().all()

    return WarehouseBoxOut(
        id=box.id,
        warehouse_id=box.warehouse_id,
        cabin_id=box.cabin_id,
        cabin_name=cabin_name,
        name=box.name,
        description=box.description,
        image_url=img_url,
        sort_order=box.sort_order,
        item_count=count,
        item_ids=list(item_ids),
        created_at=box.created_at,
    )


@router.get("/warehouses/{warehouse_id}/boxes", response_model=list[WarehouseBoxOut])
async def list_warehouse_boxes(
    warehouse_id: uuid.UUID,
    cabin_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_storekeeper),
):
    wh = await db.get(Warehouse, warehouse_id)
    if not wh:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")

    stmt = (
        select(
            WarehouseBox,
            WarehouseCabin.name.label("cabin_name"),
            func.count(ItemCabinAssignment.id).label("item_count"),
        )
        .join(WarehouseCabin, WarehouseCabin.id == WarehouseBox.cabin_id)
        .outerjoin(ItemCabinAssignment, ItemCabinAssignment.box_id == WarehouseBox.id)
        .where(WarehouseBox.warehouse_id == warehouse_id)
        .group_by(WarehouseBox.id, WarehouseCabin.name)
        .order_by(WarehouseBox.sort_order, WarehouseBox.name)
    )
    if cabin_id:
        stmt = stmt.where(WarehouseBox.cabin_id == cabin_id)

    rows = (await db.execute(stmt)).all()
    result = []
    for box, c_name, count in rows:
        result.append(await _box_out(db, box, c_name, count))
    return result


@router.post("/warehouses/{warehouse_id}/boxes", response_model=WarehouseBoxOut, status_code=status.HTTP_201_CREATED)
async def create_warehouse_box(
    warehouse_id: uuid.UUID,
    body: WarehouseBoxCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    wh = await db.get(Warehouse, warehouse_id)
    if not wh:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")
    cabin = await db.get(WarehouseCabin, body.cabin_id)
    if not cabin or cabin.warehouse_id != warehouse_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cabin not found in this warehouse")

    name = body.name.strip()
    clash = (await db.execute(
        select(WarehouseBox.id).where(
            WarehouseBox.cabin_id == body.cabin_id,
            func.lower(WarehouseBox.name) == name.lower(),
        )
    )).first()
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A box with this name already exists in this cabin")

    top = await db.scalar(
        select(func.max(WarehouseBox.sort_order)).where(WarehouseBox.cabin_id == body.cabin_id)
    )
    box = WarehouseBox(
        id=uuid.uuid4(),
        warehouse_id=warehouse_id,
        cabin_id=body.cabin_id,
        name=name,
        description=body.description,
        sort_order=body.sort_order if body.sort_order != 0 else ((top or 0) + 1),
    )
    db.add(box)
    await db.commit()
    await db.refresh(box)
    return await _box_out(db, box, cabin.name, 0)


@router.patch("/warehouses/{warehouse_id}/boxes/{box_id}", response_model=WarehouseBoxOut)
async def update_warehouse_box(
    warehouse_id: uuid.UUID,
    box_id: uuid.UUID,
    body: WarehouseBoxUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    box = await db.get(WarehouseBox, box_id)
    if not box or box.warehouse_id != warehouse_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Box not found")

    changes = body.model_dump(exclude_unset=True)
    target_cabin_id = changes.get("cabin_id", box.cabin_id)
    if "cabin_id" in changes and changes["cabin_id"] != box.cabin_id:
        cabin = await db.get(WarehouseCabin, changes["cabin_id"])
        if not cabin or cabin.warehouse_id != warehouse_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Destination cabin not found in this warehouse")

    if "name" in changes and changes["name"]:
        new_name = changes["name"].strip()
        clash = (await db.execute(
            select(WarehouseBox.id).where(
                WarehouseBox.cabin_id == target_cabin_id,
                WarehouseBox.id != box_id,
                func.lower(WarehouseBox.name) == new_name.lower(),
            )
        )).first()
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="A box with this name already exists in that cabin")
        changes["name"] = new_name

    old_cabin_id = box.cabin_id
    for k, v in changes.items():
        setattr(box, k, v)

    # When cabin_id changes, also move all items inside this box to the new cabin
    if "cabin_id" in changes and changes["cabin_id"] != old_cabin_id:
        await db.execute(
            ItemCabinAssignment.__table__.update()
            .where(ItemCabinAssignment.box_id == box_id)
            .values(cabin_id=changes["cabin_id"])
        )

    await db.commit()
    await db.refresh(box)

    count = await db.scalar(
        select(func.count(ItemCabinAssignment.id)).where(ItemCabinAssignment.box_id == box_id)
    )
    return await _box_out(db, box, count=count or 0)


@router.delete("/warehouses/{warehouse_id}/boxes/{box_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_warehouse_box(
    warehouse_id: uuid.UUID,
    box_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    box = await db.get(WarehouseBox, box_id)
    if not box or box.warehouse_id != warehouse_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Box not found")

    await db.delete(box)
    await db.commit()


@router.put("/warehouses/{warehouse_id}/boxes/{box_id}/image", response_model=WarehouseBoxOut)
async def set_box_image(
    warehouse_id: uuid.UUID,
    box_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    box = await db.get(WarehouseBox, box_id)
    if not box or box.warehouse_id != warehouse_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Box not found")

    path = f"box_{uuid.uuid4().hex}_{file.filename or 'box.jpg'}"
    await storage.upload_to_path(
        BOX_IMAGES_BUCKET, path, await file.read(), file.content_type or "image/jpeg"
    )
    box.image_bucket = BOX_IMAGES_BUCKET
    box.image_path = path
    await db.commit()
    await db.refresh(box)
    count = await db.scalar(
        select(func.count(ItemCabinAssignment.id)).where(ItemCabinAssignment.box_id == box_id)
    )
    return await _box_out(db, box, count=count or 0)


@router.delete("/warehouses/{warehouse_id}/boxes/{box_id}/image", response_model=WarehouseBoxOut)
async def remove_box_image(
    warehouse_id: uuid.UUID,
    box_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    box = await db.get(WarehouseBox, box_id)
    if not box or box.warehouse_id != warehouse_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Box not found")

    box.image_bucket = None
    box.image_path = None
    await db.commit()
    await db.refresh(box)
    count = await db.scalar(
        select(func.count(ItemCabinAssignment.id)).where(ItemCabinAssignment.box_id == box_id)
    )
    return await _box_out(db, box, count=count or 0)


@router.put("/warehouses/{warehouse_id}/boxes/{box_id}/items", response_model=WarehouseBoxOut)
async def set_box_items(
    warehouse_id: uuid.UUID,
    box_id: uuid.UUID,
    body: WarehouseBoxItemsIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    """Bulk merge/replace items assigned to a specific box."""
    box = await db.get(WarehouseBox, box_id)
    if not box or box.warehouse_id != warehouse_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Box not found")

    # Remove all existing items assigned to this box
    await db.execute(
        delete(ItemCabinAssignment).where(ItemCabinAssignment.box_id == box_id)
    )
    await db.flush()

    # Add new item assignments
    unique_item_ids = list(dict.fromkeys(body.item_ids))
    for it_id in unique_item_ids:
        item = await db.get(Item, it_id)
        if not item:
            continue
        db.add(
            ItemCabinAssignment(
                id=uuid.uuid4(),
                warehouse_id=warehouse_id,
                cabin_id=box.cabin_id,
                box_id=box_id,
                item_id=it_id,
            )
        )
        # Ensure zero-qty StockLevel exists if not present
        stock_level = (await db.execute(
            select(StockLevel).where(
                StockLevel.warehouse_id == warehouse_id,
                StockLevel.item_id == it_id,
            )
        )).scalar_one_or_none()
        if stock_level is None:
            db.add(StockLevel(
                id=uuid.uuid4(),
                warehouse_id=warehouse_id,
                item_id=it_id,
                qty=0,
            ))

    await db.commit()
    await db.refresh(box)
    return await _box_out(db, box, count=len(unique_item_ids))


# ── item cabin assignments ─────────────────────────────────────────────────

@router.get("/warehouses/{warehouse_id}/items/{item_id}/cabins", response_model=list[ItemCabinAssignmentOut])
async def get_item_cabins(
    warehouse_id: uuid.UUID,
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_storekeeper),
):
    stmt = (
        select(
            ItemCabinAssignment,
            WarehouseCabin.name.label("cabin_name"),
            WarehouseBox.name.label("box_name"),
            Item.name.label("item_name"),
        )
        .join(WarehouseCabin, WarehouseCabin.id == ItemCabinAssignment.cabin_id)
        .outerjoin(WarehouseBox, WarehouseBox.id == ItemCabinAssignment.box_id)
        .join(Item, Item.id == ItemCabinAssignment.item_id)
        .where(
            ItemCabinAssignment.warehouse_id == warehouse_id,
            ItemCabinAssignment.item_id == item_id,
        )
        .order_by(WarehouseCabin.sort_order, WarehouseCabin.name)
    )
    rows = (await db.execute(stmt)).all()
    result = []
    for assign, c_name, b_name, i_name in rows:
        result.append(
            ItemCabinAssignmentOut(
                id=assign.id,
                warehouse_id=assign.warehouse_id,
                cabin_id=assign.cabin_id,
                cabin_name=c_name,
                box_id=assign.box_id,
                box_name=b_name,
                item_id=assign.item_id,
                item_name=i_name,
                notes=assign.notes,
            )
        )
    return result


@router.put("/warehouses/{warehouse_id}/items/{item_id}/cabins", response_model=list[ItemCabinAssignmentOut])
async def set_item_cabins(
    warehouse_id: uuid.UUID,
    item_id: uuid.UUID,
    body: list[ItemCabinAssignmentIn],
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    """Place an item into one or more cabins/boxes in a warehouse.

    `[]` unassigns completely. Supports multiple placements per item.
    """
    wh = await db.get(Warehouse, warehouse_id)
    if not wh:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")

    # Validate cabin and box ownership
    for a in body:
        cabin = await db.get(WarehouseCabin, a.cabin_id)
        if cabin is None or cabin.warehouse_id != warehouse_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="One or more cabins do not belong to this warehouse")
        if a.box_id:
            box = await db.get(WarehouseBox, a.box_id)
            if box is None or box.cabin_id != a.cabin_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="One or more boxes do not belong to the specified cabin")

    await db.execute(
        delete(ItemCabinAssignment).where(
            ItemCabinAssignment.warehouse_id == warehouse_id,
            ItemCabinAssignment.item_id == item_id,
        )
    )
    await db.flush()

    seen = set()
    for a in body:
        key = (a.cabin_id, a.box_id)
        if key in seen:
            continue
        seen.add(key)
        assign = ItemCabinAssignment(
            id=uuid.uuid4(),
            warehouse_id=warehouse_id,
            cabin_id=a.cabin_id,
            box_id=a.box_id,
            item_id=item_id,
            notes=a.notes,
        )
        db.add(assign)

    if body:
        stock_level = (await db.execute(
            select(StockLevel).where(
                StockLevel.warehouse_id == warehouse_id,
                StockLevel.item_id == item_id,
            )
        )).scalar_one_or_none()
        if stock_level is None:
            db.add(StockLevel(
                id=uuid.uuid4(),
                warehouse_id=warehouse_id,
                item_id=item_id,
                qty=0,
            ))
    await db.commit()

    return await get_item_cabins(warehouse_id, item_id, db, _)


# ── item categories ─────────────────────────────────────────────────────────
#
# `items.category` stays a plain string — this table is the ops-editable
# vocabulary of allowed values, same shape as `delivery_roles` (I5-3), but
# with no FK from `items` (there is no signed document reading it, so there
# is nothing here that needs a live/frozen split). Every category is always
# editable; deleting one is refused while any item still uses it — same
# pattern as `delete_item` below, which refuses for the same reason.

@router.get("/categories", response_model=list[ItemCategoryOut])
async def list_categories(
    db: AsyncSession = Depends(get_db),
    # Read-only, and needed to render both the "new item" picker and the
    # equipment shelf filter — same reasoning as `require_storekeeper` on
    # locations.
    _: User = Depends(require_storekeeper),
):
    stmt = (
        select(ItemCategory)
        .options(selectinload(ItemCategory.subcategories))
        .order_by(ItemCategory.sort_order, ItemCategory.name)
    )
    return (await db.execute(stmt)).scalars().all()


@router.post("/categories", response_model=ItemCategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: ItemCategoryCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    name = body.name.strip().lower()
    clash = (await db.execute(
        select(ItemCategory.id).where(func.lower(ItemCategory.name) == name)
    )).first()
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A category with this name already exists")

    top = await db.scalar(select(func.max(ItemCategory.sort_order)))
    category = ItemCategory(id=uuid.uuid4(), name=name, sort_order=(top or 0) + 1)
    db.add(category)
    await db.commit()
    await db.refresh(category, ["subcategories"])
    return category


@router.patch("/categories/{category_id}", response_model=ItemCategoryOut)
async def update_category(
    category_id: uuid.UUID,
    body: ItemCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    category = await db.get(ItemCategory, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")

    changes = body.model_dump(exclude_unset=True)
    old_name = category.name
    if "name" in changes and changes["name"]:
        new_name = changes["name"].strip().lower()
        if new_name != old_name:
            clash = (await db.execute(
                select(ItemCategory.id).where(func.lower(ItemCategory.name) == new_name)
            )).first()
            if clash:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="A category with this name already exists")
        changes["name"] = new_name

    for field, value in changes.items():
        setattr(category, field, value)
    await db.commit()

    # Renaming re-labels every item already using the old name — there is no
    # FK to update, and leaving items pointing at a name the picker no longer
    # offers would strand them exactly like the legacy hardcoded columns did.
    if "name" in changes and changes["name"] != old_name:
        await db.execute(
            Item.__table__.update().where(Item.category == old_name).values(category=changes["name"])
        )
        await db.commit()

    await db.refresh(category, ["subcategories"])
    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    """Only ever deletes a category nothing uses — same reasoning as
    `delete_item`. Renaming, not deactivation, is how an unwanted category
    gets out of the way while items still hold it."""
    category = await db.get(ItemCategory, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")

    in_use = await db.scalar(
        select(func.count()).select_from(Item).where(Item.category == category.name)
    )
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"{in_use} item(s) still use this category — move them to another one first.",
        )

    await db.delete(category)
    await db.commit()


# ── subcategories ───────────────────────────────────────────────────────────

@router.post(
    "/categories/{category_id}/subcategories",
    response_model=ItemSubcategoryOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_subcategory(
    category_id: uuid.UUID,
    body: ItemSubcategoryCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    category = await db.get(ItemCategory, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")

    name = body.name.strip().lower()
    clash = (await db.execute(
        select(ItemSubcategory.id).where(
            ItemSubcategory.category_id == category_id,
            func.lower(ItemSubcategory.name) == name,
        )
    )).first()
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A subcategory with this name already exists in this category")

    top = await db.scalar(
        select(func.max(ItemSubcategory.sort_order)).where(ItemSubcategory.category_id == category_id)
    )
    subcategory = ItemSubcategory(
        id=uuid.uuid4(),
        category_id=category_id,
        name=name,
        sort_order=(top or 0) + 1,
    )
    db.add(subcategory)
    await db.commit()
    await db.refresh(subcategory)
    return subcategory


@router.patch(
    "/categories/{category_id}/subcategories/{subcategory_id}",
    response_model=ItemSubcategoryOut,
)
async def update_subcategory(
    category_id: uuid.UUID,
    subcategory_id: uuid.UUID,
    body: ItemSubcategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    subcategory = await db.get(ItemSubcategory, subcategory_id)
    if subcategory is None or subcategory.category_id != category_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Subcategory not found")
    category = await db.get(ItemCategory, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")

    changes = body.model_dump(exclude_unset=True)
    old_name = subcategory.name
    if "name" in changes and changes["name"]:
        new_name = changes["name"].strip().lower()
        if new_name != old_name:
            clash = (await db.execute(
                select(ItemSubcategory.id).where(
                    ItemSubcategory.category_id == category_id,
                    func.lower(ItemSubcategory.name) == new_name,
                )
            )).first()
            if clash:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="A subcategory with this name already exists in this category")
        changes["name"] = new_name

    for field, value in changes.items():
        setattr(subcategory, field, value)
    await db.commit()

    # Renaming re-labels every item in this category that used the old subcategory name
    if "name" in changes and changes["name"] != old_name:
        await db.execute(
            Item.__table__.update()
            .where(Item.category == category.name, Item.subcategory == old_name)
            .values(subcategory=changes["name"])
        )
        await db.commit()

    await db.refresh(subcategory)
    return subcategory


@router.delete(
    "/categories/{category_id}/subcategories/{subcategory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_subcategory(
    category_id: uuid.UUID,
    subcategory_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    subcategory = await db.get(ItemSubcategory, subcategory_id)
    if subcategory is None or subcategory.category_id != category_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Subcategory not found")
    category = await db.get(ItemCategory, category_id)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Category not found")

    in_use = await db.scalar(
        select(func.count()).select_from(Item).where(
            Item.category == category.name,
            Item.subcategory == subcategory.name,
        )
    )
    if in_use:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"{in_use} item(s) still use this subcategory — move them to another one first.",
        )

    await db.delete(subcategory)
    await db.commit()


# ── items ───────────────────────────────────────────────────────────────────

@router.get("/items", response_model=list[ItemOut])
async def list_items(
    category: str | None = None,
    subcategory: str | None = None,
    db: AsyncSession = Depends(get_db),
    # Read-only — widened 2026-08-27, same reasoning as GET /locations above:
    # a storekeeper counting a kit needs to know what's actually in it.
    _: User = Depends(require_storekeeper),
):
    stmt = select(Item).order_by(Item.category, Item.subcategory, Item.name)
    if category:
        stmt = stmt.where(Item.category == category)
    if subcategory:
        stmt = stmt.where(Item.subcategory == subcategory)
    items = (await db.execute(stmt)).scalars().all()
    return [await _item_out(i) for i in items]


def _normalize_variant_fields(data: dict) -> None:
    """A label means nothing without a group to browse it under, so clearing
    the group clears the label too. Blank strings become NULL either way —
    an empty input means "no group", not "leave whatever was there"."""
    if "variant_group" in data:
        group = (data.get("variant_group") or "").strip() or None
        data["variant_group"] = group
        if group is None:
            data["variant_label"] = None
            return
    if "variant_label" in data:
        data["variant_label"] = (data.get("variant_label") or "").strip() or None


async def _require_known_category(db: AsyncSession, category: str) -> None:
    known = await db.scalar(
        select(func.count()).select_from(ItemCategory).where(func.lower(ItemCategory.name) == category.lower())
    )
    if not known:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown category '{category}'")


async def _require_known_subcategory(db: AsyncSession, category: str, subcategory: str) -> None:
    known = await db.scalar(
        select(func.count())
        .select_from(ItemSubcategory)
        .join(ItemCategory, ItemSubcategory.category_id == ItemCategory.id)
        .where(
            func.lower(ItemCategory.name) == category.lower(),
            func.lower(ItemSubcategory.name) == subcategory.lower(),
        )
    )
    if not known:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown subcategory '{subcategory}' for category '{category}'",
        )


@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ItemCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    clash = (await db.execute(select(Item.id).where(func.lower(Item.name) == body.name.lower()))).first()
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An item with this name already exists")
    await _require_known_category(db, body.category)
    if body.subcategory:
        body.subcategory = body.subcategory.strip().lower()
        await _require_known_subcategory(db, body.category, body.subcategory)

    data = body.model_dump()
    _normalize_variant_fields(data)
    if data.get("subcategory"):
        data["subcategory"] = data["subcategory"].strip().lower()
    else:
        data["subcategory"] = None
    item = Item(id=uuid.uuid4(), **data)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return await _item_out(item)


@router.put("/items/{item_id}/image", response_model=ItemOut)
async def set_item_image(
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    """Optional photo shown to instructors picking this item off the shelf
    (B3) — same bucket/path pattern as session materials, just a different
    bucket. Replaces any existing image; the old object is left in storage,
    matching the delete_material choice of leaving orphaned bytes rather than
    risking a half-failed delete."""
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")

    path = f"{uuid.uuid4().hex}_{file.filename or 'item'}"
    await storage.upload_to_path(
        ITEM_IMAGES_BUCKET, path, await file.read(), file.content_type or "application/octet-stream"
    )
    item.image_bucket = ITEM_IMAGES_BUCKET
    item.image_path = path
    await db.commit()
    await db.refresh(item)
    return await _item_out(item)


@router.delete("/items/{item_id}/image", response_model=ItemOut)
async def remove_item_image(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")

    item.image_bucket = None
    item.image_path = None
    await db.commit()
    await db.refresh(item)
    return await _item_out(item)


@router.put("/items/{item_id}/datasheet", response_model=ItemOut)
@router.post("/items/{item_id}/datasheet", response_model=ItemOut)
async def set_item_datasheet(
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    """Optional PDF datasheet for this item (e.g. electrical/mechanical pinouts).
    Replaces any existing datasheet.
    """
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")

    path = f"{uuid.uuid4().hex}_{file.filename or 'datasheet.pdf'}"
    await storage.upload_to_path(
        ITEM_DATASHEETS_BUCKET, path, await file.read(), file.content_type or "application/pdf"
    )
    item.datasheet_bucket = ITEM_DATASHEETS_BUCKET
    item.datasheet_path = path
    await db.commit()
    await db.refresh(item)
    return await _item_out(item)


@router.delete("/items/{item_id}/datasheet", response_model=ItemOut)
async def remove_item_datasheet(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")

    item.datasheet_bucket = None
    item.datasheet_path = None
    await db.commit()
    await db.refresh(item)
    return await _item_out(item)


@router.patch("/items/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: uuid.UUID,
    body: ItemUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
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
    target_category = changes.get("category", item.category)
    if "category" in changes and changes["category"]:
        await _require_known_category(db, changes["category"])

    if "subcategory" in changes:
        if changes["subcategory"]:
            changes["subcategory"] = changes["subcategory"].strip().lower()
            await _require_known_subcategory(db, target_category, changes["subcategory"])
        else:
            changes["subcategory"] = None
    elif "category" in changes and item.subcategory:
        known_sub = await db.scalar(
            select(func.count())
            .select_from(ItemSubcategory)
            .join(ItemCategory, ItemSubcategory.category_id == ItemCategory.id)
            .where(
                func.lower(ItemCategory.name) == target_category.lower(),
                func.lower(ItemSubcategory.name) == item.subcategory.lower(),
            )
        )
        if not known_sub:
            changes["subcategory"] = None

    _normalize_variant_fields(changes)

    for field, value in changes.items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return await _item_out(item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    x_active_role: str | None = Header(None, alias="X-Active-Role"),
):
    """Destructively deletes an item and all its history/usages — restricted to admin only.

    Cleans up all references across ledger movements, stock levels, kits, templates,
    and flags so the item and all its history completely disappear.
    """
    if x_active_role and x_active_role != "admin":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Cannot delete item when active role is not admin.",
        )

    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")

    # Cascade-delete everything referencing this item across all tables
    await db.execute(delete(Movement).where(Movement.item_id == item_id))
    await db.execute(delete(StockLevel).where(StockLevel.item_id == item_id))
    await db.execute(delete(KitItem).where(KitItem.item_id == item_id))
    await db.execute(delete(KitTemplateItem).where(KitTemplateItem.item_id == item_id))
    await db.execute(delete(EquipmentReturnFlag).where(EquipmentReturnFlag.item_id == item_id))
    await db.execute(delete(ItemCabinAssignment).where(ItemCabinAssignment.item_id == item_id))

    await db.delete(item)
    await db.commit()


# ── kit templates ───────────────────────────────────────────────────────────

@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    # Read-only — widened 2026-08-27, same reasoning as GET /items above.
    _: User = Depends(require_storekeeper),
):
    return (await db.execute(select(KitTemplate).order_by(KitTemplate.code))).scalars().all()


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
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
    # Read-only — widened 2026-08-27, same reasoning as GET /items above.
    _: User = Depends(require_storekeeper),
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
                item_id=item.id, item_name=item.name, required_qty=line.required_qty,
            )
            for line, item in lines
        ],
    )


@router.patch("/templates/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    template = await db.get(KitTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template not found")

    changes = body.model_dump(exclude_unset=True)
    if "code" in changes and changes["code"]:
        new_code = changes["code"].upper()
        if new_code != template.code:
            clash = (await db.execute(
                select(KitTemplate.id).where(KitTemplate.code == new_code)
            )).first()
            if clash:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="A template with this code already exists")
        changes["code"] = new_code

    for field, value in changes.items():
        setattr(template, field, value)
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
):
    """Only ever deletes a template no physical kit was ever built from —
    same reasoning as `delete_item`. Its bill-of-materials lines cascade with
    it (kit_template_items.template_id is ON DELETE CASCADE)."""
    template = await db.get(KitTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template not found")

    in_kits = await db.scalar(select(func.count()).select_from(Kit).where(Kit.template_id == template_id))
    if in_kits:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"{in_kits} kit(s) were built from this template — retire those kits first.",
        )

    await db.delete(template)
    await db.commit()


@router.put("/templates/{template_id}/items", response_model=TemplateDetailOut)
async def set_template_items(
    template_id: uuid.UUID,
    body: list[TemplateLineIn],
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_inventory_manage),
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
