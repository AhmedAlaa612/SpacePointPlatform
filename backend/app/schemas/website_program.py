from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class WebsiteProgramOut(BaseModel):
    id: UUID
    slug: str
    title: str
    tagline: Optional[str] = None
    category: str
    level: str
    duration: str
    price_aed: int
    compare_at_price_aed: Optional[int] = None
    badge_text: Optional[str] = None
    features_list: list[str] = []
    syllabus_url: Optional[str] = None
    display_order: int
    is_published: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WebsiteProgramUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=128)
    tagline: Optional[str] = Field(default=None, max_length=255)
    category: Optional[str] = Field(default=None, max_length=64)
    level: Optional[str] = Field(default=None, max_length=64)
    duration: Optional[str] = Field(default=None, max_length=64)
    price_aed: Optional[int] = Field(default=None, ge=0)
    compare_at_price_aed: Optional[int] = Field(default=None, ge=0)
    badge_text: Optional[str] = Field(default=None, max_length=64)
    features_list: Optional[list[str]] = None
    syllabus_url: Optional[str] = Field(default=None, max_length=512)
    display_order: Optional[int] = None
    is_published: Optional[bool] = None
