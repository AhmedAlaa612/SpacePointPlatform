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


class WarehouseOut(WarehouseBase):
    id: UUID
    location_id: UUID
    location_name: str | None = None
    created_at: datetime | None = None

    class Config:
        from_attributes = True
