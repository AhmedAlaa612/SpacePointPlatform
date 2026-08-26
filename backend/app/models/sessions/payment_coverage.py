import uuid

from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class PaymentSessionCoverage(Base):
    """Which delivered sessions one payment line actually covers.

    This is the anti-double-billing key generalised from one to N.
    `services/sessions/journey.py`'s rule has always been *"a session is billed
    iff a `payment_sessions.session_id` under this instructor's own letters
    points at it"* — and one column can only point at one session. A cohort
    line covers five days, so it needs five pointers.

    `unbilled_sessions` now treats a session as billed if it is named by
    `payment_sessions.session_id` **or** by a row here under that instructor's
    letters. Existing rows keep their `session_id` untouched and need no data
    migration, and the scoped-to-this-instructor half of the rule — the part
    that stops paying the lead from hiding a session from the assistant — is
    preserved exactly.

    CASCADE on both sides: this row is meaningless without its line, and a
    deleted session takes its coverage with it. Note the asymmetry with
    `payment_sessions.session_id`, which is SET NULL precisely so a deleted
    session cannot erase a payment record — the *line* must survive, its
    coverage bookkeeping need not.
    """

    __tablename__ = "payment_session_coverage"
    __table_args__ = (
        UniqueConstraint("payment_session_id", "session_id", name="uq_payment_session_coverage"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_session_id = Column(
        UUID(as_uuid=True), ForeignKey("payment_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
