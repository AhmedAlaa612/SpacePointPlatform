from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


# ── Operations: Domain Tags Taxonomy ──────────────────────────────────────────

class MentorDomainBase(BaseModel):
    name: str
    slug: str | None = None
    category: str | None = None
    display_order: int = 0
    is_active: bool = True


class MentorDomainCreateIn(MentorDomainBase):
    pass


class MentorDomainUpdateIn(BaseModel):
    name: str | None = None
    slug: str | None = None
    category: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


class MentorDomainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    category: str | None = None
    display_order: int
    is_active: bool
    created_at: datetime


# ── Mentor Profile & Review ───────────────────────────────────────────────────

class MentorApplyIn(BaseModel):
    headline: str
    company: str
    bio: str
    missions_history: str | None = None
    what_i_can_help_with: str | None = None
    domain_ids: list[UUID] = []
    contact_mode: Literal["email", "calendar"] = "email"
    google_meet_url: str | None = None
    invite_code: str | None = None
    photo_url: str | None = None
    contact_email: EmailStr | None = None
    show_contact_button: bool = True
    linkedin_url: str | None = None
    session_duration_minutes: int | None = 30


class MentorProfileUpdateIn(BaseModel):
    headline: str | None = None
    company: str | None = None
    bio: str | None = None
    missions_history: str | None = None
    what_i_can_help_with: str | None = None
    domain_ids: list[UUID] | None = None
    contact_mode: Literal["email", "calendar"] | None = None
    google_meet_url: str | None = None
    is_published: bool | None = None
    invite_code: str | None = None
    photo_url: str | None = None
    contact_email: EmailStr | None = None
    show_contact_button: bool | None = None
    linkedin_url: str | None = None
    session_duration_minutes: int | None = None


class MentorProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    slug: str
    headline: str | None = None
    company: str | None = None
    bio: str | None = None
    missions_history: str | None = None
    what_i_can_help_with: str | None = None
    contact_mode: str
    google_meet_url: str | None = None
    status: str
    is_active: bool
    is_published: bool = True
    invite_code: str | None = None
    photo_url: str | None = None
    contact_email: str | None = None
    show_contact_button: bool = True
    linkedin_url: str | None = None
    session_duration_minutes: int
    total_completed_minutes: int
    completed_sessions_count: int
    domains: list[MentorDomainOut] = []
    created_at: datetime
    # User info populated when joined
    user_full_name: str | None = None
    user_email: str | None = None
    user_photo_url: str | None = None
    user_country: str | None = None


class MentorPhotoUploadOut(BaseModel):
    photo_url: str


class MentorReviewIn(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str | None = None


class MentorStatusUpdateIn(BaseModel):
    is_active: bool
    status: Literal["applied", "approved", "rejected", "suspended"] | None = None


# ── Mentor Availability & Slots ───────────────────────────────────────────────

class MentorAvailabilityIn(BaseModel):
    day_of_week: int | None = None  # 0=Mon, 6=Sun (None for specific date)
    specific_date: date | None = None
    start_time: time
    end_time: time
    timezone: str = "UTC"
    is_active: bool = True


class MentorAvailabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mentor_id: UUID
    day_of_week: int | None = None
    specific_date: date | None = None
    start_time: time
    end_time: time
    timezone: str
    is_active: bool


class AvailableSlotOut(BaseModel):
    start: datetime
    end: datetime
    available: bool = True


# ── Bookings & Inquiries ──────────────────────────────────────────────────────

class MentorBookIn(BaseModel):
    mentee_name: str
    mentee_email: EmailStr
    topics: str
    scheduled_start: datetime | None = None  # Required if booking_type == 'session'
    booking_type: Literal["session", "inquiry"] = "session"


class MentorBookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mentor_id: UUID
    mentee_name: str
    mentee_email: str
    topics: str
    booking_type: str
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    status: str
    created_at: datetime
    mentor_name: str | None = None
