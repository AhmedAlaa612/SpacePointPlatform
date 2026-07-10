import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import ENUM, UUID

from app.db.base import Base
from app.models.enums import ApplicationStatus


class ApplicationReview(Base):
    """The applicant pipeline state machine (instructors/HANDOFF.md §4).
    Transitions: in_progress -> under_review -> {phase_1_approved | rejected}
    -> under_review (phase 2) -> {approved | rejected}; rejected -> in_progress (reopen).
    """

    __tablename__ = "application_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    status = Column(
        ENUM(ApplicationStatus, name="application_status", create_type=False),
        nullable=False,
        default=ApplicationStatus.in_progress,
    )
    admin_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    feedback = Column(String, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    # When the applicant submitted their application for review (status
    # in_progress -> under_review). Distinct from created_at (when they started
    # the application) and reviewed_at (when an admin actioned it). NULL while
    # still in_progress. sql/0018 backfills historical rows best-effort.
    submitted_at = Column(DateTime(timezone=True), nullable=True)
