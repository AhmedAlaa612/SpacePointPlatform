from datetime import datetime
import re
from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

_DAY_NUM_RE = re.compile(r"^day\s*(\d+)\b", re.IGNORECASE)
_DAY_ONLY_RE = re.compile(r"^day\s*(\d+)\s*$", re.IGNORECASE)


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
    images: list[str] = Field(default_factory=list)
    items: list[dict] = Field(default_factory=list)
    days: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_stage(self) -> "CaseStudyStructureSection":
        clean_imgs: list[str] = []
        for u in self.images or []:
            if isinstance(u, str) and u.strip() and u.strip() not in clean_imgs:
                clean_imgs.append(u.strip())
        primary = (self.image_url or "").strip()
        if primary and primary not in clean_imgs:
            clean_imgs.insert(0, primary)
        self.images = clean_imgs
        self.image_url = clean_imgs[0] if clean_imgs else None

        merged_items: list[dict] = []
        for it in self.items or []:
            if not isinstance(it, dict):
                continue
            t = str(it.get("title") or it.get("day_title") or "").strip()
            desc = str(it.get("description") or "").strip()
            raw_chips = it.get("milestones") if it.get("milestones") is not None else it.get("chips")
            miles = (
                [str(m).strip() for m in raw_chips if str(m).strip()]
                if isinstance(raw_chips, list)
                else []
            )
            merged_items.append({"title": t, "description": desc, "milestones": miles})

        if self.days:
            matched: set[int] = set()
            for d in self.days:
                if not isinstance(d, dict):
                    continue
                dt = str(d.get("day_title") or d.get("title") or "").strip()
                d_desc = str(d.get("description") or "").strip()
                raw_m = d.get("milestones")
                d_miles = (
                    [str(m).strip() for m in raw_m if str(m).strip()]
                    if isinstance(raw_m, list)
                    else []
                )
                if not dt and not d_desc and not d_miles:
                    continue

                match_idx: int | None = None
                for idx, cur in enumerate(merged_items):
                    if idx in matched:
                        continue
                    cur_t = cur["title"]
                    if dt and cur_t.lower() == dt.lower():
                        match_idx = idx
                        break
                    m_dt_only = _DAY_ONLY_RE.match(dt)
                    m_cur_day = _DAY_NUM_RE.match(cur_t)
                    if m_dt_only and m_cur_day and int(m_dt_only.group(1)) == int(m_cur_day.group(1)):
                        match_idx = idx
                        break
                    m_cur_only = _DAY_ONLY_RE.match(cur_t)
                    m_dt_day = _DAY_NUM_RE.match(dt)
                    if m_cur_only and m_dt_day and int(m_cur_only.group(1)) == int(m_dt_day.group(1)):
                        cur["title"] = dt
                        match_idx = idx
                        break

                if match_idx is not None:
                    matched.add(match_idx)
                    existing_m = merged_items[match_idx]["milestones"]
                    for m in d_miles:
                        if m not in existing_m:
                            existing_m.append(m)
                    if d_desc and not merged_items[match_idx]["description"]:
                        merged_items[match_idx]["description"] = d_desc
                else:
                    merged_items.append({"title": dt, "description": d_desc, "milestones": d_miles})

            self.days = []

        self.items = merged_items
        return self


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
    live_linked: bool | None = None
    overrides: dict[str, Any] | None = None
    hidden_sections: list[str] | None = None


class WebsiteCaseStudyOut(WebsiteCaseStudyBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    live_linked: bool = False
    overrides: dict[str, Any] = Field(default_factory=dict)
    hidden_sections: list[str] = Field(default_factory=list)
    preview_token: str | None = None
    field_states: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class CreateCaseStudyFromProgramIn(BaseModel):
    program_id: UUID
    cohort_ids: list[UUID] = Field(default_factory=list)
    title: str | None = None
    include_buckets: list[str] | None = None


class ResetFieldIn(BaseModel):
    field: str


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
