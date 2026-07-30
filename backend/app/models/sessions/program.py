import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Program(Base):
    """A workshop/camp/course/sponsorship template — e.g. 'CubeSat Workshop
    2026-Q3'. Cohorts (below) are the actual runs of a program with real dates,
    a location, and registrations."""

    __tablename__ = "programs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Format like SATKIT-WS-2026-Q3, validated in the service layer, not the DB.
    code = Column(String(32), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    program_type = Column(String(24), nullable=False)  # workshop|course|session
    description = Column(Text, nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    # I5-2. Same three-level fallback shape as `price`: set here, overridable
    # on the cohort, overridable again on the session. The payment line
    # prefills from whatever the chain resolves to.
    duration_hours = Column(Numeric(5, 2), nullable=True)
    pricing_model = Column(String(24), nullable=False)  # paid|free
    default_capacity = Column(Integer, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    # Per-program completion requirement for cohort completion/certificates
    # (W5 S5-3 follow-up, operator request — was a hardcoded global 0.7).
    # "percentage": completion_rule_value is 0-100, compared against
    # present/total_sessions. "session_count": completion_rule_value is a
    # whole number of sessions the student must have been marked present for.
    completion_rule_type = Column(String(16), nullable=False, default="percentage")
    completion_rule_value = Column(Numeric(6, 2), nullable=False, default=70)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
