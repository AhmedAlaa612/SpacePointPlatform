from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class MaterialCreate(BaseModel):
    title: str
    description: Optional[str] = None
    link: str
    category: Optional[str] = None


class MaterialUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    link: Optional[str] = None
    category: Optional[str] = None


class MaterialOut(BaseModel):
    id: UUID
    created_by: Optional[UUID] = None
    title: str
    description: Optional[str] = None
    link: str
    category: Optional[str] = None
    created_at: datetime
    created_by_name: Optional[str] = None

    class Config:
        from_attributes = True
