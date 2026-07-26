import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Registration(Base):
    """A student's registration for one cohort — the commercial record. The
    ticket (token + QR) IS this row; there is no separate tickets table.
    One registration per (contact, cohort): a repeat student re-registering
    for a different cohort of the same program is a new row with is_repeat=True."""

    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("contact_id", "cohort_id", name="uq_registration_contact_cohort"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False)
    payer_contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False)

    price_charged = Column(Numeric(10, 2), nullable=True)
    payment_status = Column(String(16), nullable=False, default="unpaid")  # unpaid|partial|paid|waived|refunded
    status = Column(String(16), nullable=False, default="registered")  # registered|attended|completed|cancelled|no_show

    source_campaign_id = Column(UUID(as_uuid=True), nullable=True)  # plain UUID until marketing tables land
    source_touchpoint_id = Column(UUID(as_uuid=True), ForeignKey("touchpoints.id", ondelete="SET NULL"), nullable=True)
    is_repeat = Column(Boolean, nullable=False, default=False)

    # The ticket credential — long and random, never a guessable sequential id.
    # QR codes encode a URL built from this token (see services/sessions/registration.py, R1-4).
    ticket_token = Column(String(64), unique=True, nullable=False)
    ticket_sent_at = Column(DateTime(timezone=True), nullable=True)
    registered_via = Column(String(16), nullable=False)  # form|import|desk
    import_batch_id = Column(UUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RegistrationSession(Base):
    """Which specific Session(s) within the cohort a registration actually
    covers — a cohort can have several sessions and a student may only be
    signed up for some of them (different pricing, different schedule).

    No rows for a registration means "covers every session in the cohort" —
    the default for the common single-session workshop, and for a
    registration made before every session has been generated yet. Only
    write rows here when the caller explicitly picked a subset."""

    __tablename__ = "registration_sessions"
    __table_args__ = (
        UniqueConstraint("registration_id", "session_id", name="uq_registration_session"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    registration_id = Column(UUID(as_uuid=True), ForeignKey("registrations.id", ondelete="CASCADE"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
