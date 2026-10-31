import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class WebsiteCaseStudy(Base):
    """A public Case Study / Mission showcase on `spacepoint.ae/case-studies`.

    Can be:
    - Standalone (Manual data entry)
    - Linked to a single Cohort, multiple Cohorts, or an entire Program
      for dynamic snapshotting and metrics re-sync.

    Follows a standardized 7-section modular template where any empty or
    toggled-off section is omitted on the public site:
    1. Header & Collaboration Bar (Title, category badge, partner logos)
    2. Overview & Key Impact Metrics (Rich text + 2-5 metric counters, optional hero metric)
    3. Photo Gallery & Lightbox (2x2 preview grid + full lightbox)
    4. Core Highlights & Capabilities (Card highlights, curriculum chapters)
    5. Program Structure & Formats (Phases/Weeks accordions or format cards)
    6. Visibility, Showcases & Spotlights (Media metrics + showcase banners/stories)
    7. Student Voices & Report CTA (Testimonials quote cards + PDF flyer/report link)
    """

    __tablename__ = "website_case_studies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(128), nullable=False, unique=True, index=True)

    title = Column(String(255), nullable=False)
    subtitle = Column(String(255), nullable=True)
    category = Column(String(64), nullable=False, default="Other")  # e.g. Roadshows, Universities, National Programs, Challenges & Competitions
    card_summary = Column(Text, nullable=False)
    cover_image_url = Column(String(512), nullable=False)
    partner_logo_url = Column(String(512), nullable=True)
    partner_name = Column(String(255), nullable=True)

    # Source Relationship (optional link to Portal data)
    source_type = Column(String(32), nullable=False, default="manual")  # manual | cohort | multi_cohort | program
    program_id = Column(
        UUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    cohort_id = Column(
        UUID(as_uuid=True),
        ForeignKey("cohorts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # List of UUID strings if multi-cohort
    cohort_ids = Column(JSONB, nullable=False, default=list, server_default="[]")

    # 1. Header & Collaboration Bar
    # [{ "name": "UAE Space Agency", "logo_url": "...", "role": "In collaboration with" }]
    partners = Column(JSONB, nullable=False, default=list, server_default="[]")

    # 2. Overview & Key Impact Metrics
    overview_text = Column(Text, nullable=True)
    # [{ "value": "464", "label": "Participants", "is_hero": false }, ...]
    metrics = Column(JSONB, nullable=False, default=list, server_default="[]")
    hero_metric_value = Column(String(128), nullable=True)
    hero_metric_label = Column(String(255), nullable=True)
    hero_metric_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    # Quick card metrics (e.g. indices or custom [{ "value": "50", "label": "Students" }])
    card_metrics = Column(JSONB, nullable=False, default=list, server_default="[]")

    # 3. Photo Gallery
    # ["/assets/img/Case studies/PLANETX/Planet1.jpg", ...]
    gallery_images = Column(JSONB, nullable=False, default=list, server_default="[]")

    # 4. Core Highlights, Capabilities & Curriculum
    # [{ "title": "Electrical Integration", "description": "...", "icon": "cpu" }]
    highlights = Column(JSONB, nullable=False, default=list, server_default="[]")
    # [{ "chapter_num": "Ch. 1", "title": "Intro to Sat", "icon": "sat" }]
    curriculum_chapters = Column(JSONB, nullable=False, default=list, server_default="[]")

    # 5. Program Structure & Formats
    structure_title = Column(String(255), nullable=True)  # e.g. "Bootcamp Structure" or "Program Formats"
    # [
    #   {
    #     "id": "week-1",
    #     "badge": "01",
    #     "title": "Week 1 - Online",
    #     "subtitle": "Foundational Skills & CAD Modeling Preparation",
    #     "image_url": "...",
    #     "items": [
    #       { "title": "CAD Modeling Masterclass", "description": "..." },
    #       { "title": "Engineering Tasks & Mentorship", "description": "..." }
    #     ]
    #   },
    #   {
    #     "id": "week-2",
    #     "badge": "02",
    #     "title": "Week 2 - OnSite",
    #     "subtitle": "Practical Lander Integration, Testing & Final Presentations",
    #     "days": [
    #       { "day_title": "Day 1 - Launch & Foundation", "milestones": ["SatKit Workshop", "..."] }
    #     ]
    #   }
    # ]
    structure_sections = Column(JSONB, nullable=False, default=list, server_default="[]")

    # 6. Visibility, Showcases & Spotlights
    # [{ "value": "23,000+", "label": "views on day 4 alone", "icon": "eye" }]
    visibility_stats = Column(JSONB, nullable=False, default=list, server_default="[]")
    # [
    #   {
    #     "type": "showcase" | "spotlight" | "future_mission",
    #     "title": "Presented at GITEX GLOBAL",
    #     "subtitle": "...",
    #     "tag": "Showcased & Presented",
    #     "logo_url": "...",
    #     "images": ["...", "..."],
    #     "content": "..."
    #   }
    # ]
    spotlights = Column(JSONB, nullable=False, default=list, server_default="[]")

    # 7. Student Voices & Report CTA
    # [
    #   {
    #     "quote": "...",
    #     "author_name": "Mohammed Salem Ibrahim",
    #     "author_role": "Student Participant",
    #     "author_photo_url": "...",
    #     "badge": "Space42 Students Voice"
    #   }
    # ]
    testimonials = Column(JSONB, nullable=False, default=list, server_default="[]")
    cta_label = Column(String(255), nullable=True)
    cta_url = Column(String(512), nullable=True)

    # Controls
    display_order = Column(Integer, nullable=False, default=0)
    is_featured = Column(Boolean, nullable=False, default=False, server_default="false")
    is_published = Column(Boolean, nullable=False, default=True, server_default="true")

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
