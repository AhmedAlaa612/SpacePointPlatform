"""Schemas for LMS Program & Cohort CubeSat Component Configuration."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class ComponentConfigIn(BaseModel):
    disabled_subsystems: list[str] = Field(default_factory=list)
    disabled_tags: list[str] = Field(default_factory=list)
    disabled_component_ids: list[UUID] = Field(default_factory=list)


class ComponentItemSummary(BaseModel):
    id: UUID
    component_name: str
    subsystem: str
    tag: str | None = None
    component_code: str | None = None
    example_role: str | None = None
    scaled_mass_g: float | None = None
    voltage_v: float | None = None
    current_ma: float | None = None
    assumed_cost_usd: float | None = None
    image_url: str | None = None
    is_active: bool = True
    is_enabled: bool = True


class ComponentConfigOut(BaseModel):
    owner_type: str  # 'program' | 'cohort'
    owner_id: UUID
    is_inherited: bool = False
    has_override: bool = False
    disabled_subsystems: list[str] = Field(default_factory=list)
    disabled_tags: list[str] = Field(default_factory=list)
    disabled_component_ids: list[UUID] = Field(default_factory=list)
    available_subsystems: list[str] = Field(default_factory=list)
    available_tags: list[str] = Field(default_factory=list)
    total_components: int = 0
    enabled_components: int = 0
    components: list[ComponentItemSummary] = Field(default_factory=list)
    updated_at: datetime | None = None
    updated_by: UUID | None = None
