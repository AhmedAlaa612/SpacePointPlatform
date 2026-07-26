import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
