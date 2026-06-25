from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class TrainingVideoOut(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    notes: Optional[str] = None
    sort_order: int
    is_completed: bool = False

    class Config:
        from_attributes = True


class TrainingModuleOut(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    sort_order: int
    videos: list[TrainingVideoOut] = []

    class Config:
        from_attributes = True


class TrainingModuleCreate(BaseModel):
    title: str
    description: Optional[str] = None
    sort_order: int = 1


class TrainingVideoCreate(BaseModel):
    module_id: UUID
    title: str
    description: Optional[str] = None
    notes: Optional[str] = None
    sort_order: int = 1


class LibraryResourceOut(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    format: str
    file_url: str

    class Config:
        from_attributes = True


class LibraryModuleOut(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    resources: list[LibraryResourceOut] = []

    class Config:
        from_attributes = True


class LibraryModuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
