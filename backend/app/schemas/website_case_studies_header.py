from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class CaseStudyHeaderStat(BaseModel):
    value: str = Field(..., description="e.g. 1,000+ or 15+")
    label: str = Field(..., description="e.g. Students Trained or Institutions")


class CaseStudyHeaderPartner(BaseModel):
    name: str = Field(..., description="e.g. Higher Colleges of Technology")
    logo_url: str = Field(..., description="Logo image path or upload URL")
    website_url: str | None = Field(default="", description="Optional URL to partner site")


class WebsiteCaseStudiesHeaderOut(BaseModel):
    id: int = 1
    stats: list[CaseStudyHeaderStat] = Field(default_factory=list)
    partners: list[CaseStudyHeaderPartner] = Field(default_factory=list)
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class WebsiteCaseStudiesHeaderUpdate(BaseModel):
    stats: list[CaseStudyHeaderStat] = Field(default_factory=list)
    partners: list[CaseStudyHeaderPartner] = Field(default_factory=list)
