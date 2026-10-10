from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class LabProjectOut(BaseModel):
    id: UUID
    title: str
    slug: str
    badges: list[str] = []
    description: str
    project_url: str
    cta_label: str
    cover_image_url: Optional[str] = None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LabProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    slug: Optional[str] = Field(default=None, max_length=128)
    badges: list[str] = []
    description: str = Field(min_length=1)
    project_url: str = Field(default="/miura-ori", max_length=512)
    cta_label: str = Field(default="Launch Project →", max_length=128)
    cover_image_url: Optional[str] = Field(default=None, max_length=512)
    display_order: int = 0
    is_active: bool = True


class LabProjectUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=128)
    badges: Optional[list[str]] = None
    description: Optional[str] = Field(default=None, min_length=1)
    project_url: Optional[str] = Field(default=None, max_length=512)
    cta_label: Optional[str] = Field(default=None, max_length=128)
    cover_image_url: Optional[str] = Field(default=None, max_length=512)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
