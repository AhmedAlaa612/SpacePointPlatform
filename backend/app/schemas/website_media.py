from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MediaClippingOut(BaseModel):
    id: UUID
    publisher_name: str
    article_title: str
    article_url: str
    published_date: str
    logo_url: Optional[str] = None
    is_arabic: bool
    snippet: Optional[str] = None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MediaClippingCreate(BaseModel):
    publisher_name: str = Field(min_length=1, max_length=255)
    article_title: str = Field(min_length=1, max_length=255)
    article_url: str = Field(min_length=1, max_length=512)
    published_date: str = Field(default="", max_length=64)
    logo_url: Optional[str] = Field(default=None, max_length=512)
    is_arabic: bool = False
    snippet: Optional[str] = None
    display_order: int = 0
    is_active: bool = True


class MediaClippingUpdate(BaseModel):
    publisher_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    article_title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    article_url: Optional[str] = Field(default=None, min_length=1, max_length=512)
    published_date: Optional[str] = Field(default=None, max_length=64)
    logo_url: Optional[str] = Field(default=None, max_length=512)
    is_arabic: Optional[bool] = None
    snippet: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
