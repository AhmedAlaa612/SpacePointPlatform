from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class WarehouseBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    code: str | None = Field(None, max_length=32)
    address: str | None = None
    notes: str | None = None
    is_active: bool = True


class WarehouseCreate(WarehouseBase):
    location_id: UUID


class WarehouseUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    code: str | None = Field(None, max_length=32)
    location_id: UUID | None = None
    address: str | None = None
    notes: str | None = None
    is_active: bool | None = None


# ── Warehouse Boxes ──────────────────────────────────────────────────────────

class WarehouseBoxBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    sort_order: int = 0


class WarehouseBoxCreate(WarehouseBoxBase):
    cabin_id: UUID


class WarehouseBoxUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    cabin_id: UUID | None = None
    description: str | None = None
    sort_order: int | None = None


class WarehouseBoxOut(WarehouseBoxBase):
    id: UUID
    warehouse_id: UUID
    cabin_id: UUID
    cabin_name: str | None = None
    image_url: str | None = None
    item_count: int = 0
    item_ids: list[UUID] = []
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class WarehouseBoxItemsIn(BaseModel):
    item_ids: list[UUID]


# ── Warehouse Cabins ─────────────────────────────────────────────────────────

class WarehouseCabinBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = None
    pin_x: float | None = None
    pin_y: float | None = None
    sort_order: int = 0


class WarehouseCabinCreate(WarehouseCabinBase):
    pass


class WarehouseCabinUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    description: str | None = None
    pin_x: float | None = None
    pin_y: float | None = None
    sort_order: int | None = None


class WarehouseCabinOut(WarehouseCabinBase):
    id: UUID
    warehouse_id: UUID
    image_url: str | None = None
    box_count: int = 0
    boxes: list[WarehouseBoxOut] = []
    item_count: int = 0
    created_at: datetime | None = None

    class Config:
        from_attributes = True


# ── Item Cabin Assignments ───────────────────────────────────────────────────

class ItemCabinAssignmentIn(BaseModel):
    cabin_id: UUID
    box_id: UUID | None = None
    notes: str | None = None


class ItemCabinAssignmentOut(BaseModel):
    id: UUID
    warehouse_id: UUID
    cabin_id: UUID
    cabin_name: str
    box_id: UUID | None = None
    box_name: str | None = None
    item_id: UUID
    item_name: str | None = None
    notes: str | None = None

    class Config:
        from_attributes = True


class WarehouseOut(WarehouseBase):
    id: UUID
    location_id: UUID
    location_name: str | None = None
    image_url: str | None = None
    cabins: list[WarehouseCabinOut] = []
    created_at: datetime | None = None

    class Config:
        from_attributes = True
