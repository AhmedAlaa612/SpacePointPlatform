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

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations, require_storekeeper
from app.db.session import get_db
from app.models.inventory.city import City
from app.models.inventory.item import Item
from app.models.inventory.item_category import ItemCategory
from app.models.inventory.kit import Kit, KitItem
from app.models.inventory.kit_template import KitTemplate, KitTemplateItem
from app.models.inventory.location import Location
from app.models.inventory.warehouse import Warehouse
from app.models.inventory.stock import StockLevel
from app.models.user import User
from app.schemas.inventory.warehouse import (
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


async def _item_out(item: Item) -> ItemOut:
    out = ItemOut.model_validate(item)
    out.image_url = await storage.resolve_url(item.image_bucket, item.image_path)
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
    # Read-only, and `require_storekeeper` admits storekeeper *or* operations.
    # Every write below stays `require_operations`. A storekeeper cannot record
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
    _: User = Depends(require_operations),
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
    _: User = Depends(require_operations),
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
    _: User = Depends(require_operations),
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
    _: User = Depends(require_operations),
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
    result = []
    for wh, loc_name in rows:
        out = WarehouseOut.model_validate(wh)
        out.location_name = loc_name
        result.append(out)
    return result


@router.post("/warehouses", response_model=WarehouseOut, status_code=status.HTTP_201_CREATED)
async def create_warehouse(
    body: WarehouseCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    location = await db.get(Location, body.location_id)
    if not location:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Parent location not found")

    wh = Warehouse(id=uuid.uuid4(), **body.model_dump())
    db.add(wh)
    await db.commit()
    await db.refresh(wh)

    out = WarehouseOut.model_validate(wh)
    out.location_name = location.name
    return out


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseOut)
async def update_warehouse(
    warehouse_id: uuid.UUID,
    body: WarehouseUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
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
    out = WarehouseOut.model_validate(wh)
    out.location_name = location.name if location else None
    return out


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
    stmt = select(ItemCategory).order_by(ItemCategory.sort_order, ItemCategory.name)
    return (await db.execute(stmt)).scalars().all()


@router.post("/categories", response_model=ItemCategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: ItemCategoryCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
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
    await db.refresh(category)
    return category


@router.patch("/categories/{category_id}", response_model=ItemCategoryOut)
async def update_category(
    category_id: uuid.UUID,
    body: ItemCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
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

    await db.refresh(category)
    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
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


@router.post("/items", response_model=ItemOut, status_code=status.HTTP_201_CREATED)
async def create_item(
    body: ItemCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    clash = (await db.execute(select(Item.id).where(func.lower(Item.name) == body.name.lower()))).first()
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="An item with this name already exists")
    await _require_known_category(db, body.category)

    data = body.model_dump()
    _normalize_variant_fields(data)
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
    _: User = Depends(require_operations),
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
    _: User = Depends(require_operations),
):
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")

    item.image_bucket = None
    item.image_path = None
    await db.commit()
    await db.refresh(item)
    return await _item_out(item)


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
    if "category" in changes and changes["category"]:
        await _require_known_category(db, changes["category"])
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
    _: User = Depends(require_operations),
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
    _: User = Depends(require_operations),
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
