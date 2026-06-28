from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class TrainingVideoOut(BaseModel):
    id: UUID
    title: str
    description: Optional[str] = None
    notes: Optional[str] = None
    video_url: str = ""
    sort_order: int
    is_completed: bool = False

    model_config = {"from_attributes": True, "populate_by_name": True}

    @classmethod
    def from_orm_video(cls, v: object, is_completed: bool = False) -> "TrainingVideoOut":
        return cls(
            id=getattr(v, "id"),
            title=getattr(v, "title"),
            description=getattr(v, "description"),
            notes=getattr(v, "notes"),
            video_url=getattr(v, "video_path", "") or "",
            sort_order=getattr(v, "sort_order"),
            is_completed=is_completed,
        )


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
    file_url: str          # signed URL at response time (not stored value)
    resource_type: str = "file"

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
