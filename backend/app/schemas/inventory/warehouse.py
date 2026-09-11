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
    item_count: int = 0
    created_at: datetime | None = None

    class Config:
        from_attributes = True


class ItemCabinAssignmentIn(BaseModel):
    cabin_id: UUID
    qty: int | None = None
    notes: str | None = None
    is_primary: bool = True


class ItemCabinAssignmentOut(BaseModel):
    id: UUID
    warehouse_id: UUID
    cabin_id: UUID
    cabin_name: str
    item_id: UUID
    item_name: str | None = None
    qty: int | None = None
    notes: str | None = None
    is_primary: bool = True

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
