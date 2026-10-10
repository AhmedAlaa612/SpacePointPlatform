from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class NewsletterOut(BaseModel):
    id: UUID
    title: str
    issue_date: str
    cover_url: Optional[str] = None
    file_url: str
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NewsletterCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    issue_date: str = Field(min_length=1, max_length=64)
    cover_url: Optional[str] = Field(default=None, max_length=512)
    file_url: str = Field(min_length=1, max_length=512)
    display_order: int = 0
    is_active: bool = True


class NewsletterUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    issue_date: Optional[str] = Field(default=None, min_length=1, max_length=64)
    cover_url: Optional[str] = Field(default=None, max_length=512)
    file_url: Optional[str] = Field(default=None, min_length=1, max_length=512)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class LeadOut(BaseModel):
    id: UUID
    email: str
    lead_type: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class NewsletterSubscribeIn(BaseModel):
    email: EmailStr
