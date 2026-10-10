from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FaqOut(BaseModel):
    id: UUID
    category: str
    question: str
    answer: str
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FaqCreate(BaseModel):
    category: str = Field(default="General", max_length=64)
    question: str = Field(min_length=1, max_length=255)
    answer: str = Field(min_length=1)
    display_order: int = 0
    is_active: bool = True


class FaqUpdate(BaseModel):
    category: Optional[str] = Field(default=None, max_length=64)
    question: Optional[str] = Field(default=None, min_length=1, max_length=255)
    answer: Optional[str] = Field(default=None, min_length=1)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
