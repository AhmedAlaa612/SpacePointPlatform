from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class MegaEventBase(BaseModel):
    slug: str
    country: str = "uae"
    title: str
    title_ar: str | None = None
    subtitle: str | None = None
    tagline: str | None = None
    banner_url: str | None = None
    top_banner_url: str | None = None
    date_label: str | None = None
    about_text: str | None = None
    official_note: str | None = None
    official_url: str | None = None
    primary_cta_label: str | None = None
    primary_cta_url: str | None = None
    at_a_glance: list[dict[str, Any]] = Field(default_factory=list)
    host_steps: list[dict[str, Any]] = Field(default_factory=list)
    coordinator_info: dict[str, Any] = Field(default_factory=dict)
    partners: list[dict[str, Any]] = Field(default_factory=list)
    faqs: list[dict[str, Any]] = Field(default_factory=list)
    default_language: str = "en"
    ar_content: dict[str, Any] = Field(default_factory=dict)
    display_order: int = 0
    is_published: bool = True


class MegaEventCreate(MegaEventBase):
    slug: str | None = None


class MegaEventUpdate(BaseModel):
    slug: str | None = None
    country: str | None = None
    title: str | None = None
    title_ar: str | None = None
    subtitle: str | None = None
    tagline: str | None = None
    banner_url: str | None = None
    top_banner_url: str | None = None
    date_label: str | None = None
    about_text: str | None = None
    official_note: str | None = None
    official_url: str | None = None
    primary_cta_label: str | None = None
    primary_cta_url: str | None = None
    at_a_glance: list[dict[str, Any]] | None = None
    host_steps: list[dict[str, Any]] | None = None
    coordinator_info: dict[str, Any] | None = None
    partners: list[dict[str, Any]] | None = None
    faqs: list[dict[str, Any]] | None = None
    default_language: str | None = None
    ar_content: dict[str, Any] | None = None
    display_order: int | None = None
    is_published: bool | None = None


class MegaEventOut(MegaEventBase):
    id: UUID
    events_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WebsiteEventBase(BaseModel):
    slug: str
    mega_event_id: UUID | None = None
    organization_id: UUID | None = None
    cohort_id: UUID | None = None

    country: str = "uae"
    city: str | None = None
    event_type: str = "competition"
    audience: str | None = None
    venue_type: str | None = "onsite"

    # 1. Hero
    title: str
    title_ar: str | None = None
    subtitle: str | None = None
    tagline: str | None = None
    banner_url: str | None = None
    top_banner_url: str | None = None
    host_org_name: str | None = None
    date_label: str | None = None
    location: str | None = None
    registration_url: str | None = None
    guidelines_url: str | None = None
    wsw_official_url: str | None = None

    # 2. About & Benefits
    about_text: str | None = None
    benefits: list[dict[str, Any]] = Field(default_factory=list)

    # 3. At a Glance
    at_a_glance: list[dict[str, Any]] = Field(default_factory=list)

    # 4. Eligibility
    eligibility_intro: str | None = None
    eligibility_rows: list[dict[str, Any]] = Field(default_factory=list)
    eligibility_note: str | None = None

    # 5. Journey
    journey_stages: list[dict[str, Any]] = Field(default_factory=list)

    # 6. Timeline
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    timeline_note: str | None = None

    # 7. Deliverables
    deliverables: list[dict[str, Any]] = Field(default_factory=list)
    deliverables_note: str | None = None

    # 8. Final Showcase & Awards
    awards_text: str | None = None

    # 9. Registration
    registration_text: str | None = None
    registration_deadline: str | None = None
    whatsapp_url: str | None = None
    registration_note: str | None = None

    # 10. FAQs
    faqs: list[dict[str, Any]] = Field(default_factory=list)

    # 11. Partners
    partners: list[dict[str, Any]] = Field(default_factory=list)
    partners_note: str | None = None

    # 12. Contacts
    contacts: list[dict[str, Any]] = Field(default_factory=list)
    contact_meta: list[dict[str, Any]] = Field(default_factory=list)

    default_language: str = "en"
    ar_content: dict[str, Any] = Field(default_factory=dict)

    display_order: int = 0
    is_published: bool = False


class WebsiteEventCreate(WebsiteEventBase):
    slug: str | None = None


class WebsiteEventUpdate(BaseModel):
    slug: str | None = None
    mega_event_id: UUID | None = None
    organization_id: UUID | None = None
    cohort_id: UUID | None = None

    country: str | None = None
    city: str | None = None
    event_type: str | None = None
    audience: str | None = None
    venue_type: str | None = None

    title: str | None = None
    title_ar: str | None = None
    subtitle: str | None = None
    tagline: str | None = None
    banner_url: str | None = None
    top_banner_url: str | None = None
    host_org_name: str | None = None
    date_label: str | None = None
    location: str | None = None
    registration_url: str | None = None
    guidelines_url: str | None = None
    wsw_official_url: str | None = None

    about_text: str | None = None
    benefits: list[dict[str, Any]] | None = None
    at_a_glance: list[dict[str, Any]] | None = None

    eligibility_intro: str | None = None
    eligibility_rows: list[dict[str, Any]] | None = None
    eligibility_note: str | None = None

    journey_stages: list[dict[str, Any]] | None = None
    timeline: list[dict[str, Any]] | None = None
    timeline_note: str | None = None

    deliverables: list[dict[str, Any]] | None = None
    deliverables_note: str | None = None

    awards_text: str | None = None

    registration_text: str | None = None
    registration_deadline: str | None = None
    whatsapp_url: str | None = None
    registration_note: str | None = None

    faqs: list[dict[str, Any]] | None = None
    partners: list[dict[str, Any]] | None = None
    partners_note: str | None = None
    contacts: list[dict[str, Any]] | None = None
    contact_meta: list[dict[str, Any]] | None = None

    default_language: str | None = None
    ar_content: dict[str, Any] | None = None

    display_order: int | None = None
    is_published: bool | None = None


class WebsiteEventOut(WebsiteEventBase):
    id: UUID
    mega_event_slug: str | None = None
    mega_event_title: str | None = None
    organization_name: str | None = None
    created_by_user_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrganizationAccountCreateIn(BaseModel):
    """Admin-initiated or self-signup payload for an Organization + User account."""
    org_name_latin: str
    org_name_arabic: str | None = None
    org_type: str = "university"  # school|university|sponsor|government|ngo|company|other
    country: str = "uae"
    city: str | None = None
    full_name: str
    email: EmailStr
    phone: str | None = None
    password: str

    is_approved: bool = True
    can_publish_events: bool = False
    can_author_courses: bool = True
    can_publish_courses: bool = False
    course_scope_all: bool = False
    allowed_course_ids: list[str] = Field(default_factory=list)
    max_events: int | None = None
    max_programs: int | None = None
    max_cohorts: int | None = None
    max_students_per_cohort: int | None = None
    max_observers_per_cohort: int | None = None


class OrganizationAccountUpdateIn(BaseModel):
    """Admin update payload for an Organization and its linked User account."""
    org_name_latin: str | None = None
    org_name_arabic: str | None = None
    org_type: str | None = None
    country: str | None = None
    city: str | None = None
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    password: str | None = None

    is_approved: bool | None = None
    can_publish_events: bool | None = None
    can_author_courses: bool | None = None
    can_publish_courses: bool | None = None
    course_scope_all: bool | None = None
    allowed_course_ids: list[str] | None = None
    max_events: int | None = None
    max_programs: int | None = None
    max_cohorts: int | None = None
    max_students_per_cohort: int | None = None
    max_observers_per_cohort: int | None = None


class OrganizationSummaryOut(BaseModel):
    id: UUID
    name_latin: str
    name_arabic: str | None = None
    org_type: str
    country: str | None = None
    city: str | None = None
    owner_user_id: UUID | None = None
    owner_email: str | None = None
    owner_name: str | None = None
    owner_phone: str | None = None
    owner_status: str | None = None
    events_count: int = 0
    members_count: int = 1

    is_approved: bool = True
    can_publish_events: bool = False
    can_author_courses: bool = True
    can_publish_courses: bool = False
    course_scope_all: bool = False
    allowed_course_ids: list[str] = Field(default_factory=list)
    max_events: int | None = None
    max_programs: int | None = None
    max_cohorts: int | None = None
    max_students_per_cohort: int | None = None
    max_observers_per_cohort: int | None = None


class OrgTeamMemberOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None = None
    status: str
    created_at: datetime
    is_owner: bool = False


class OrgTeamMemberCreateIn(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    phone: str | None = None
