import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class CohortInterest(Base):
    """"Notify me" — a contact's signal that they want to know when a
    `planned` (not-yet-open) public cohort starts taking registrations.
    Deliberately not a `Registration` row: no payment/attendance/ticket state
    applies to "just interested," and a `Registration` would misleadingly
    imply they've actually signed up (2026-08-07).

    Resolved through the same `resolve_or_create_contact` identity flow as
    real registration, so interest dedupes against and shows up on the same
    contact record — not an anonymous, disconnected capture.
    """

    __tablename__ = "cohort_interest"
    __table_args__ = (
        UniqueConstraint("contact_id", "cohort_id", name="uq_cohort_interest_contact_cohort"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True)
    # Set once send_cohort_interest_notifications has emailed this contact —
    # lets the job be re-run safely (e.g. a later ops correction reopening
    # the cohort) without spamming someone twice for the same open.
    notified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
