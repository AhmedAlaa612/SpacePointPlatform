from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class WebsitePolicyOut(BaseModel):
    id: UUID
    slug: str
    title: str
    eyebrow: Optional[str] = None
    meta: Optional[str] = None
    summary: Optional[str] = None
    content_html: str
    display_order: int
    is_active: bool
    show_in_footer: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WebsitePolicySummaryOut(BaseModel):
    id: UUID
    slug: str
    title: str
    eyebrow: Optional[str] = None
    meta: Optional[str] = None
    summary: Optional[str] = None
    display_order: int
    is_active: bool
    show_in_footer: bool
    updated_at: datetime

    class Config:
        from_attributes = True


class WebsitePolicyCreate(BaseModel):
    slug: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    eyebrow: Optional[str] = Field(default=None, max_length=128)
    meta: Optional[str] = Field(default=None, max_length=255)
    summary: Optional[str] = None
    content_html: str = Field(min_length=1)
    display_order: int = 0
    is_active: bool = True
    show_in_footer: bool = True


class WebsitePolicyUpdate(BaseModel):
    slug: Optional[str] = Field(default=None, min_length=1, max_length=128)
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    eyebrow: Optional[str] = Field(default=None, max_length=128)
    meta: Optional[str] = Field(default=None, max_length=255)
    summary: Optional[str] = None
    content_html: Optional[str] = Field(default=None, min_length=1)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
    show_in_footer: Optional[bool] = None
