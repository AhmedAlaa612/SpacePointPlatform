from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class ModuleCreate(BaseModel):
    title: str = "General"
    description: Optional[str] = None


class ModuleUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class ModuleOut(BaseModel):
    id: UUID
    epic_id: UUID
    title: str
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
