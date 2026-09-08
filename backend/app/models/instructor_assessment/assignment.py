import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class AssessmentCohortAssignment(Base):
    """The on/off switch (operator ask, 2026-09): a cohort with no row here
    has no assessment requirement at all — registering interest on any of
    its calls behaves exactly as it did before this domain existed. A row
    here names which `AssessmentConfig` gates every call opened on this
    cohort from then on.

    Deliberately no per-cohort question snapshot (unlike `GameSessionAssignment`,
    which needs one because ops edits a session's own copy of the questions):
    nothing here asks for a cohort to have its own edited question set, so a
    plain reference is enough. Already-registered applicants are never
    retroactively required to take a newly-assigned assessment — this row
    only gates *new* interest registrations from the moment it's set.
    """

    __tablename__ = "assessment_cohort_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, unique=True)
    config_id = Column(UUID(as_uuid=True), ForeignKey("assessment_configs.id", ondelete="RESTRICT"), nullable=False)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
