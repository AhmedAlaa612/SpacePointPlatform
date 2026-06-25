import re
from pydantic import BaseModel, field_validator
from typing import Optional
from uuid import UUID


class BadgeBase(BaseModel):
    label: str
    description: Optional[str] = None
    icon: Optional[str] = None
    criteria_type: str
    threshold: int = 1
    sort_order: int = 0
    audience: str = "ambassador"  # ambassador | teacher


class BadgeCreate(BadgeBase):
    code: Optional[str] = None  # auto-slugged from label when omitted

    @field_validator("code")
    @classmethod
    def slug(cls, v):
        return v


class BadgeUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    criteria_type: Optional[str] = None
    threshold: Optional[int] = None
    sort_order: Optional[int] = None
    audience: Optional[str] = None


class BadgeOut(BadgeBase):
    id: UUID
    code: str

    class Config:
        from_attributes = True


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:50] or "badge"
