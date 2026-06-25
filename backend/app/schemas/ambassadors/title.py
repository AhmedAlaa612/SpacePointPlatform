from pydantic import BaseModel
from typing import Optional
from uuid import UUID


class TitleBase(BaseModel):
    name: str
    min_points: int = 0
    icon: Optional[str] = None
    color: Optional[str] = None
    sort_order: int = 0
    audience: str = "ambassador"  # ambassador | teacher


class TitleCreate(TitleBase):
    pass


class TitleUpdate(BaseModel):
    name: Optional[str] = None
    min_points: Optional[int] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    audience: Optional[str] = None


class TitleOut(TitleBase):
    id: UUID

    class Config:
        from_attributes = True
