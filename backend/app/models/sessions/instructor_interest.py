import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class InstructorInterest(Base):
    """An instructor's 'I'd like to give this session' signal on an open-call
    session — the marketplace's pre-selection step. Distinct from
    SessionInstructor (models/sessions/session.py), which is the actual
    per-session assignment once someone is picked.

    Session-scoped as of 2026-07-24 (W4) — was cohort-scoped in the original
    spec, moved to match both the CEO's own description ("a session is made
    available...") and how assignment itself already works (per session, not
    per cohort). See MASTER_EXECUTION_PLAN_V2.md's W4 discoveries entry.
    """

    __tablename__ = "instructor_interests"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_instructor_interest"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    note = Column(Text, nullable=True)
    # I5-5. "I have read and agree to the responsibilities." The text itself
    # is versioned in `portal_settings` (key `instructor.responsibilities`);
    # this records *when* they agreed and to *which* version, so a later edit
    # to the text cannot retroactively change what someone accepted.
    responsibilities_accepted_at = Column(DateTime(timezone=True), nullable=True)
    responsibilities_version = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
