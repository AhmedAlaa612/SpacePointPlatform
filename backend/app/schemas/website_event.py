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
    quiz_scope: str = "all"
    allowed_quiz_template_ids: list[str] = Field(default_factory=list)
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
    quiz_scope: str | None = None
    allowed_quiz_template_ids: list[str] | None = None
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
    created_at: datetime | None = None
    owner_user_id: UUID | None = None
    owner_email: str | None = None
    owner_name: str | None = None
    owner_phone: str | None = None
    owner_status: str | None = None
    owner_card_id: str | None = None
    logo_url: str | None = None
    events_count: int = 0
    published_events_count: int = 0
    members_count: int = 1
    programs_count: int = 0
    cohorts_count: int = 0
    running_cohorts_count: int = 0
    enrolled_students_count: int = 0
    highest_cohort_students: int = 0
    highest_cohort_name: str | None = None
    highest_cohort_observers: int = 0
    highest_observers_cohort_name: str | None = None
    authored_courses_count: int = 0
    pending_review_courses_count: int = 0
    shared_courses_count: int = 0
    invite_batches_active_count: int = 0
    invite_used_count: int = 0
    invite_max_count: int = 0
    quiz_templates_authored_count: int = 0
    quiz_questions_authored_count: int = 0

    is_approved: bool = True
    can_publish_events: bool = False
    can_author_courses: bool = True
    can_publish_courses: bool = False
    course_scope_all: bool = False
    allowed_course_ids: list[str] = Field(default_factory=list)
    quiz_scope: str = "own"
    allowed_quiz_template_ids: list[str] = Field(default_factory=list)
    max_events: int | None = None
    max_programs: int | None = None
    max_cohorts: int | None = None
    max_students_per_cohort: int | None = None
    max_observers_per_cohort: int | None = None


class OrgProgramChecklistItemOut(BaseModel):
    id: UUID
    position: int
    title: str
    item_type: str
    optional: bool = False
    scope: str = "individual"


class OrgProgramDetailOut(BaseModel):
    id: UUID
    name: str
    program_type: str
    active: bool = True
    lms_program_id: UUID | None = None
    checklist_name: str | None = None
    certificate_required: bool = True
    cohorts_count: int = 0
    checklist_items: list[OrgProgramChecklistItemOut] = Field(default_factory=list)


class OrgCohortDetailOut(BaseModel):
    id: UUID
    program_id: UUID
    program_name: str
    name: str
    status: str
    starts_on: str | None = None
    ends_on: str | None = None
    enrolled_count: int = 0
    capacity: int | None = None
    observers_count: int = 0
    sessions_count: int = 0
    completion_pct: int = 0


class OrgInviteBatchOut(BaseModel):
    id: UUID
    code: str
    label: str | None = None
    kind: str
    granted_target: str | None = None
    used_count: int = 0
    max_uses: int = 0
    expires_at: datetime | None = None
    is_active: bool = True


class OrgStudentDetailOut(BaseModel):
    registration_id: UUID
    contact_id: UUID
    user_id: UUID | None = None
    full_name: str
    email: str | None = None
    phone: str | None = None
    cohort_id: UUID
    cohort_name: str
    status: str
    enrolled_at: datetime
    completion_pct: int = 0


class OrgAuthoredCourseOut(BaseModel):
    id: UUID
    title: str
    track: str | None = None
    is_published: bool = False
    submitted_for_review_at: datetime | None = None
    modules_count: int = 0
    enrolled_count: int = 0
    created_at: datetime | None = None


class OrgSharedCourseOut(BaseModel):
    id: UUID
    title: str
    track: str | None = None
    level: str | None = None
    modules_count: int = 0
    is_published: bool = True


class OrgQuizTemplateOut(BaseModel):
    id: UUID
    name: str
    questions_count: int = 0
    is_active: bool = True
    linked_cohorts: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class OrgLandingPageOut(BaseModel):
    id: UUID
    title: str
    slug: str
    country: str
    is_published: bool = False
    cohort_id: UUID | None = None
    cohort_name: str | None = None
    registrations_count: int = 0
    updated_at: datetime


class OrgTeamMemberDetailOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str
    phone: str | None = None
    role: str
    card_id: str | None = None
    status: str
    invite_pending: bool = False
    observer_cohorts: list[str] = Field(default_factory=list)


class OrganizationDetailOut(BaseModel):
    organization: OrganizationSummaryOut
    programs: list[OrgProgramDetailOut] = Field(default_factory=list)
    cohorts: list[OrgCohortDetailOut] = Field(default_factory=list)
    invite_batches: list[OrgInviteBatchOut] = Field(default_factory=list)
    students: list[OrgStudentDetailOut] = Field(default_factory=list)
    authored_courses: list[OrgAuthoredCourseOut] = Field(default_factory=list)
    shared_courses: list[OrgSharedCourseOut] = Field(default_factory=list)
    quiz_templates: list[OrgQuizTemplateOut] = Field(default_factory=list)
    landing_pages: list[OrgLandingPageOut] = Field(default_factory=list)
    team: list[OrgTeamMemberDetailOut] = Field(default_factory=list)


class OrgTeamMemberOut(BaseModel):
    id: UUID
    full_name: str
    email: str
    phone: str | None = None
    status: str
    created_at: datetime
    is_owner: bool = False
    # Only meaningful on create: whether the set-password invite email went out.
    invite_email_sent: bool = False
    # Invited but hasn't set a password / signed in yet.
    invite_pending: bool = False
    # True when an existing SpacePoint account was attached instead of created.
    existing_account: bool = False


class OrgTeamMemberCreateIn(BaseModel):
    full_name: str
    email: EmailStr
    # Optional: when omitted the member gets a random unusable password and
    # sets their own via the "Reset Link" flow.
    password: str | None = None
    phone: str | None = None
