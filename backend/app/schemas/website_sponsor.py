from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

SponsorTier = Literal["client", "partner", "supporter", "academic", "industry_leader"]


class SponsorOut(BaseModel):
    id: UUID
    name: str
    logo_url: str
    logo_hover_url: Optional[str] = None
    website_url: Optional[str] = None
    tier: str
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SponsorsGroupedOut(BaseModel):
    """Grouped shape the marketing site's getSponsors() already consumes."""

    clients: list[SponsorOut] = []
    partners: list[SponsorOut] = []
    supporters: list[SponsorOut] = []
    academic: list[SponsorOut] = []
    industry_leaders: list[SponsorOut] = []


class SponsorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    logo_url: str = Field(min_length=1, max_length=512)
    logo_hover_url: Optional[str] = Field(default=None, max_length=512)
    tier: SponsorTier = "partner"
    website_url: Optional[str] = Field(default=None, max_length=512)
    display_order: int = 0
    is_active: bool = True


class SponsorUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    logo_url: Optional[str] = Field(default=None, min_length=1, max_length=512)
    logo_hover_url: Optional[str] = Field(default=None, max_length=512)
    tier: Optional[SponsorTier] = None
    website_url: Optional[str] = Field(default=None, max_length=512)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
