from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class CaseStudyPartnerItem(BaseModel):
    name: str
    logo_url: str = ""
    role: str | None = None


class CaseStudyMetricItem(BaseModel):
    value: str
    label: str
    is_hero: bool = False


class CaseStudyHighlightItem(BaseModel):
    title: str
    description: str
    icon: str | None = None


class CaseStudyCurriculumChapter(BaseModel):
    chapter_num: str
    title: str
    icon: str | None = None


class CaseStudyStructureSection(BaseModel):
    id: str | None = None
    badge: str | None = None
    title: str
    subtitle: str | None = None
    description: str | None = None
    image_url: str | None = None
    items: list[dict] = Field(default_factory=list)
    days: list[dict] = Field(default_factory=list)


class CaseStudyVisibilityStat(BaseModel):
    value: str
    label: str
    icon: str | None = None


class CaseStudySpotlightItem(BaseModel):
    type: str = "showcase"  # showcase | spotlight | future_mission
    title: str
    subtitle: str | None = None
    tag: str | None = None
    logo_url: str | None = None
    images: list[str] = Field(default_factory=list)
    content: str | None = None


class CaseStudyTestimonialItem(BaseModel):
    quote: str
    author_name: str
    author_role: str = "Student Participant"
    author_photo_url: str | None = None
    badge: str | None = None


class WebsiteCaseStudyBase(BaseModel):
    title: str
    subtitle: str | None = None
    slug: str | None = None
    category: str = "Other"
    card_summary: str
    cover_image_url: str
    partner_logo_url: str | None = None
    partner_name: str | None = None

    source_type: str = "manual"  # manual | cohort | multi_cohort | program
    program_id: UUID | None = None
    cohort_id: UUID | None = None
    cohort_ids: list[UUID | str] = Field(default_factory=list)

    partners: list[CaseStudyPartnerItem] = Field(default_factory=list)
    overview_text: str | None = None
    metrics: list[CaseStudyMetricItem] = Field(default_factory=list)
    hero_metric_value: str | None = None
    hero_metric_label: str | None = None
    hero_metric_enabled: bool = False
    card_metrics: list[CaseStudyMetricItem] = Field(default_factory=list)

    gallery_images: list[str] = Field(default_factory=list)
    highlights: list[CaseStudyHighlightItem] = Field(default_factory=list)
    curriculum_chapters: list[CaseStudyCurriculumChapter] = Field(default_factory=list)

    structure_title: str | None = None
    structure_sections: list[CaseStudyStructureSection] = Field(default_factory=list)

    visibility_stats: list[CaseStudyVisibilityStat] = Field(default_factory=list)
    spotlights: list[CaseStudySpotlightItem] = Field(default_factory=list)

    testimonials: list[CaseStudyTestimonialItem] = Field(default_factory=list)
    cta_label: str | None = None
    cta_url: str | None = None

    display_order: int = 0
    is_featured: bool = False
    is_published: bool = True


class WebsiteCaseStudyCreate(WebsiteCaseStudyBase):
    pass


class WebsiteCaseStudyUpdate(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    slug: str | None = None
    category: str | None = None
    card_summary: str | None = None
    cover_image_url: str | None = None
    partner_logo_url: str | None = None
    partner_name: str | None = None

    source_type: str | None = None
    program_id: UUID | None = None
    cohort_id: UUID | None = None
    cohort_ids: list[UUID | str] | None = None

    partners: list[CaseStudyPartnerItem] | None = None
    overview_text: str | None = None
    metrics: list[CaseStudyMetricItem] | None = None
    hero_metric_value: str | None = None
    hero_metric_label: str | None = None
    hero_metric_enabled: bool | None = None
    card_metrics: list[CaseStudyMetricItem] | None = None

    gallery_images: list[str] | None = None
    highlights: list[CaseStudyHighlightItem] | None = None
    curriculum_chapters: list[CaseStudyCurriculumChapter] | None = None

    structure_title: str | None = None
    structure_sections: list[CaseStudyStructureSection] | None = None

    visibility_stats: list[CaseStudyVisibilityStat] | None = None
    spotlights: list[CaseStudySpotlightItem] | None = None

    testimonials: list[CaseStudyTestimonialItem] | None = None
    cta_label: str | None = None
    cta_url: str | None = None

    display_order: int | None = None
    is_featured: bool | None = None
    is_published: bool | None = None


class WebsiteCaseStudyOut(WebsiteCaseStudyBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    created_at: datetime
    updated_at: datetime


class CaseStudySnapshotRequest(BaseModel):
    source_type: str  # cohort | multi_cohort | program
    cohort_id: UUID | None = None
    cohort_ids: list[UUID | str] = Field(default_factory=list)
    program_id: UUID | None = None


class CaseStudySnapshotOut(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    category: str | None = None
    card_summary: str | None = None
    overview_text: str | None = None
    partner_name: str | None = None
    partner_logo_url: str | None = None
    partners: list[CaseStudyPartnerItem] = Field(default_factory=list)
    metrics: list[CaseStudyMetricItem] = Field(default_factory=list)
    card_metrics: list[CaseStudyMetricItem] = Field(default_factory=list)
    curriculum_chapters: list[CaseStudyCurriculumChapter] = Field(default_factory=list)
    structure_sections: list[CaseStudyStructureSection] = Field(default_factory=list)
