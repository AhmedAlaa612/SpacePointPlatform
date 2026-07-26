import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ContactRoleEvent(Base):
    """One role gained or lost by a contact, at a point in time — the audit
    trail behind "when did this person become an instructor" (operator
    request, 2026-07-24). `role` is whatever vocabulary was actually mutated
    at the point of change: a raw `users.roles` value (applicant, instructor,
    intern, admin, ...) when a staff account's roles are edited, or a
    `contacts.contact_roles` value (student, parent_guardian, ...) when a
    contact-only record changes. Both share this one table since they're the
    same concept — a role appearing or disappearing for a person — just at
    different vocabularies depending on where the edit happened.

    Deliberately NOT retroactive: role changes that happened before this
    table existed have no event here (there's no reliable date to attach to
    them) — the timeline starts from whenever this shipped.
    """

    __tablename__ = "contact_role_events"
    __table_args__ = (
        Index("ix_contact_role_events_contact_occurred", "contact_id", "occurred_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)

    role = Column(String(32), nullable=False)
    action = Column(String(8), nullable=False)  # added|removed

    # registration|desk|import|contact_edit|user_role_edit|user_created|
    # backfill_initial — where the mutation that produced this event came from.
    source = Column(String(24), nullable=False)

    # Who did it, for the human-driven sources (contact_edit, user_role_edit).
    # NULL for system-driven sources (registration, import, backfill_initial).
    changed_by_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    occurred_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
