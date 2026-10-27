import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class Organization(Base):
    """A school, sponsor, B2B client, or government body — the entity behind a
    private cohort (see sessions.Cohort.organization_id) or a sponsor_rep/
    school_admin contact."""

    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name_latin = Column(String(255), nullable=False)
    name_arabic = Column(String(255), nullable=True)
    org_type = Column(String(24), nullable=False)  # school|university|sponsor|government|ngo|company|other
    country = Column(String(64), nullable=True)
    city = Column(String(64), nullable=True)

    # contacts already exists by the time this table is created, but contacts
    # also FKs back to organizations — deferred via use_alter to break the cycle.
    primary_contact_id = Column(
        UUID(as_uuid=True),
        ForeignKey("contacts.id", ondelete="SET NULL", use_alter=True, name="fk_organizations_primary_contact_id"),
        nullable=True,
    )
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)

    # ── Hosting Grants & Quotas ──────────────────────────────────────────
    is_approved = Column(Boolean, nullable=False, default=False, server_default="false")
    can_publish_events = Column(Boolean, nullable=False, default=False, server_default="false")
    can_author_courses = Column(Boolean, nullable=False, default=True, server_default="true")
    can_publish_courses = Column(Boolean, nullable=False, default=False, server_default="false")
    course_scope_all = Column(Boolean, nullable=False, default=False, server_default="false")
    # Specific SpacePoint Course IDs this organization is allowed to attach to its cohorts
    allowed_course_ids = Column(JSONB, nullable=False, default=list, server_default="[]")

    # Quiz Bank & Question Access: 'all' | 'selected' | 'own'
    quiz_scope = Column(String(32), nullable=False, default="own", server_default="'own'")
    # Specific SpacePoint Quiz Template IDs this organization is allowed to access
    allowed_quiz_template_ids = Column(JSONB, nullable=False, default=list, server_default="[]")

    # Constraints (NULL = unlimited)
    max_events = Column(Integer, nullable=True)
    max_programs = Column(Integer, nullable=True)
    max_cohorts = Column(Integer, nullable=True)
    max_students_per_cohort = Column(Integer, nullable=True)
    max_observers_per_cohort = Column(Integer, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
