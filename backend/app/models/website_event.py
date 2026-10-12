import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class MegaEvent(Base):
    """An umbrella campaign / multi-event festival on the public website
    (e.g. World Space Week UAE — `/events/uae/wsw`).

    Contains a hero, overview text, highlights/stats, coordinator info, and
    aggregates all published `WebsiteEvent` rows where `mega_event_id == id`.
    """

    __tablename__ = "mega_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(128), nullable=False, unique=True, index=True)
    country = Column(String(64), nullable=False, default="uae", index=True)

    title = Column(String(255), nullable=False)
    title_ar = Column(String(255), nullable=True)
    subtitle = Column(String(255), nullable=True)
    tagline = Column(String(512), nullable=True)
    banner_url = Column(String(512), nullable=True)
    top_banner_url = Column(String(512), nullable=True)
    date_label = Column(String(128), nullable=True)

    about_text = Column(Text, nullable=True)
    official_note = Column(Text, nullable=True)
    official_url = Column(String(512), nullable=True)
    primary_cta_label = Column(String(128), nullable=True)
    primary_cta_url = Column(String(512), nullable=True)

    # [{ "highlight": "XX Events", "details": "Across the UAE" }, ...]
    at_a_glance = Column(JSONB, nullable=False, default=list, server_default="[]")
    # [{ "stage": "Step 1", "title": "Develop your event", "description": "..." }, ...]
    host_steps = Column(JSONB, nullable=False, default=list, server_default="[]")
    # { "name": "Abdullah AlSalmani", "role": "UAE National Coordinator – World Space Week", "email": "...", "note": "..." }
    coordinator_info = Column(JSONB, nullable=False, default=dict, server_default="{}")
    # [{ "name": "...", "role": "...", "logo_url": "..." }, ...]
    partners = Column(JSONB, nullable=False, default=list, server_default="[]")
    # [{ "question": "...", "answer": "..." }, ...]
    faqs = Column(JSONB, nullable=False, default=list, server_default="[]")

    display_order = Column(Integer, nullable=False, default=0)
    is_published = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class WebsiteEvent(Base):
    """A public event landing page on `spacepoint.ae/events/{country}/{slug}`
    (e.g. SatForge UAE 2026 — `/events/uae/satforge-2026`).

    Follows the standardized 12-section event publication structure:
    1. Hero Banner
    2. About & Why Participate (benefits)
    3. At a Glance (numerical/key highlights)
    4. Who Can Participate (Eligibility table & notes)
    5. Event / Competition Journey (Stage 1..N)
    6. Timeline / Important Dates
    7. Requirements & Deliverables (Expandable Phases + budget/notes)
    8. Final Showcase & Awards
    9. Registration (Form link, deadline, WhatsApp team-formation link)
    10. Frequently Asked Questions
    11. Organizers & Supporting Partners
    12. Contact & Further Information

    If an organization leaves any section blank/empty, the public landing page
    simply omits that section. Organizations can create & edit their own events,
    while only Admins can publish/unpublish (`is_published`).
    """

    __tablename__ = "website_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(128), nullable=False, unique=True, index=True)

    mega_event_id = Column(
        UUID(as_uuid=True),
        ForeignKey("mega_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    organization_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Routing & Directory Filter Metadata
    country = Column(String(64), nullable=False, default="uae", index=True)
    city = Column(String(64), nullable=True)  # e.g. Abu Dhabi, Al Ain, Dubai, Sharjah
    event_type = Column(String(64), nullable=False, default="competition")  # competition|workshop|talk|exhibition|panel|hackathon|stargazing|other
    audience = Column(String(128), nullable=True)  # Universities, Schools, Public, Professionals
    venue_type = Column(String(32), nullable=True, default="onsite")  # onsite|online|hybrid

    # 1. Hero Banner
    title = Column(String(255), nullable=False)
    title_ar = Column(String(255), nullable=True)
    subtitle = Column(String(255), nullable=True)
    tagline = Column(String(512), nullable=True)
    banner_url = Column(String(512), nullable=True)
    top_banner_url = Column(String(512), nullable=True)
    host_org_name = Column(String(255), nullable=True)
    date_label = Column(String(128), nullable=True)
    location = Column(String(255), nullable=True)
    registration_url = Column(String(512), nullable=True)
    guidelines_url = Column(String(512), nullable=True)
    wsw_official_url = Column(String(512), nullable=True)

    # 2. About & Why Participate
    about_text = Column(Text, nullable=True)
    # [{ "title": "Hands-on engineering experience", "description": "Apply theory to mission design..." }, ...]
    benefits = Column(JSONB, nullable=False, default=list, server_default="[]")

    # 3. At a Glance
    # [{ "highlight": "Target participation", "details": "Approximately 500 students (indicative)" }, ...]
    at_a_glance = Column(JSONB, nullable=False, default=list, server_default="[]")

    # 4. Who Can Participate (Eligibility)
    eligibility_intro = Column(Text, nullable=True)
    # [{ "label": "Enrollment", "requirement": "Currently enrolled at a UAE university..." }, ...]
    eligibility_rows = Column(JSONB, nullable=False, default=list, server_default="[]")
    eligibility_note = Column(Text, nullable=True)

    # 5. Journey
    # [{ "stage": "Stage 1", "title": "Form Your Team & Register", "description": "..." }, ...]
    journey_stages = Column(JSONB, nullable=False, default=list, server_default="[]")

    # 6. Timeline / Important Dates
    # [{ "date": "11 October", "milestone": "Student team registration opens" }, ...]
    timeline = Column(JSONB, nullable=False, default=list, server_default="[]")
    timeline_note = Column(Text, nullable=True)

    # 7. Requirements & Deliverables
    # [{ "phase": "Phase 1 — Digital Design & Simulation", "deadline": "30 October 2026, 12:00 PM (noon)", "items": ["..."] }, ...]
    deliverables = Column(JSONB, nullable=False, default=list, server_default="[]")
    deliverables_note = Column(Text, nullable=True)

    # 8. Final Competition / Showcase & Awards
    awards_text = Column(Text, nullable=True)

    # 9. Registration Section
    registration_text = Column(Text, nullable=True)
    registration_deadline = Column(String(255), nullable=True)
    whatsapp_url = Column(String(512), nullable=True)
    registration_note = Column(Text, nullable=True)

    # 10. Frequently Asked Questions
    # [{ "question": "...", "answer": "..." }, ...]
    faqs = Column(JSONB, nullable=False, default=list, server_default="[]")

    # 11. Organizers & Supporting Partners
    # [{ "name": "Abu Dhabi University", "role": "Host Institution", "logo_url": "" }, ...]
    partners = Column(JSONB, nullable=False, default=list, server_default="[]")
    partners_note = Column(Text, nullable=True)

    # 12. Contact & Further Information
    # [{ "name": "Dr. Jawad Yousaf", "role": "College of Engineering...", "organization": "Abu Dhabi University", "email": "jawad.yousaf@adu.ac.ae" }, ...]
    contacts = Column(JSONB, nullable=False, default=list, server_default="[]")
    # [{ "label": "Host institution", "value": "Abu Dhabi University — Al Ain Campus", "url": "" }, ...]
    contact_meta = Column(JSONB, nullable=False, default=list, server_default="[]")

    display_order = Column(Integer, nullable=False, default=0)
    is_published = Column(Boolean, nullable=False, default=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
