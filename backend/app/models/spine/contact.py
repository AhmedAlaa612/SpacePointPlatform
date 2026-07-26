import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy import Index

from app.db.base import Base


class Contact(Base):
    """The one identity behind a person, across every domain and role they ever
    hold — a student registering for a workshop today may be an instructor
    next year. Contacts are never deleted; duplicates are soft-retired via
    merged_into_id (see services/spine/identity.py) rather than removed, so
    every table that references a contact keeps a valid, if redirected, link.
    """

    __tablename__ = "contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Just a name — no script/language assumption. Was split into
    # full_name_latin/full_name_arabic; collapsed to one free-text field since
    # a name can be in either script and nothing here should presume which.
    full_name = Column(String(255), nullable=False)

    # student, parent_guardian, teacher, school_admin, sponsor_rep, gov_official,
    # alumnus, instructor, ambassador, intern, other — a contact can hold several.
    contact_roles = Column(ARRAY(String(32)), nullable=False, default=list)

    primary_phone_e164 = Column(String(20), nullable=True, index=True)
    whatsapp_e164 = Column(String(20), nullable=True, index=True)
    secondary_phones = Column(ARRAY(String(20)), nullable=False, default=list)
    email = Column(String(255), nullable=True, index=True)
    preferred_language = Column(String(8), nullable=False, default="ar")
    country = Column(String(64), nullable=True)
    city = Column(String(64), nullable=True)

    # subscriber|lead|mql|sql|customer|alumni
    lifecycle_stage = Column(String(24), nullable=False, default="subscriber")

    # Re-added 2026-07-24 at the CEO's explicit request, after having been
    # removed entirely earlier the same day — purely informational, plain
    # stored data. No age/minor enforcement is reintroduced anywhere in the
    # system; that policy (parent info always optional, never gated) is
    # unchanged. See MASTER_EXECUTION_PLAN_V2.md §DISCOVERIES.
    date_of_birth = Column(Date, nullable=True)
    # Free text (e.g. "Grade 8", "Year 5") rather than an enum — school
    # systems vary (American/British/etc.), and nothing here validates or
    # acts on the value.
    grade = Column(String(32), nullable=True)

    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)

    # touchpoints doesn't exist yet when this table is first created — deferred
    # via use_alter so the two tables can reference each other (added post-create).
    source_touchpoint_id = Column(
        UUID(as_uuid=True),
        ForeignKey("touchpoints.id", ondelete="SET NULL", use_alter=True, name="fk_contacts_source_touchpoint_id"),
        nullable=True,
    )

    merged_into_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_contacts_contact_roles", "contact_roles", postgresql_using="gin"),
    )


class ContactRelationship(Base):
    """Household/guardian links between contacts — e.g. a parent's contact row
    linked to their child's, so consent and payer lookups can walk the graph."""

    __tablename__ = "contact_relationships"
    __table_args__ = (
        UniqueConstraint("contact_id", "related_contact_id", "relation", name="uq_contact_relationship"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    related_contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    relation = Column(String(24), nullable=False)  # guardian_of|child_of|sibling_of|spouse_of|other
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
