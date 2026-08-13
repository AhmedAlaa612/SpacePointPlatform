import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import ENUM, UUID

from app.db.base import Base
from app.models.enums import CertificateType


class Certificate(Base):
    """Shared certificate table (PLAN §4.5), unified with a `type` discriminator
    so workshop-delivery certs (instructors domain, Phase 3), completion certs
    (interns/instructors, Phase 4), and student session-completion certs (W5
    S5-3) all live in one place. `payment_session_id` and the workshop_*
    fields are only populated for type='workshop_delivery'; `contact_id`/
    `registration_id` only for type='student_completion' — exactly one of
    `user_id`/`contact_id` is set, never both, never neither (see the CHECK
    constraint below): staff certs are user-owned, student certs are
    contact-owned, since a public registrant never gets a User row."""

    __tablename__ = "certificates"
    __table_args__ = (
        CheckConstraint("(user_id IS NOT NULL) != (contact_id IS NOT NULL)", name="ck_certificate_exactly_one_owner"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=True, index=True)
    registration_id = Column(UUID(as_uuid=True), ForeignKey("registrations.id", ondelete="SET NULL"), nullable=True)
    type = Column(ENUM(CertificateType, name="certificate_type", create_type=False), nullable=False)
    file_url = Column(String, nullable=True)   # populated for instructor workshop_delivery certs only;
    # student_completion certs are emailed directly — no storage upload, no URL stored here.
    bucket = Column(String(100), nullable=True)
    file_path = Column(String, nullable=True)  # storage path; URLs generated at query time via storage.resolve_url
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # workshop_delivery-only fields (nullable for completion-cert rows)
    payment_session_id = Column(
        UUID(as_uuid=True), ForeignKey("payment_sessions.id", ondelete="SET NULL"), nullable=True
    )
    workshop_name = Column(String(255), nullable=True)
    workshop_date = Column(String(50), nullable=True)
    location = Column(String(255), nullable=True)

    # LMS-only (2026-08-13) — what was completed to earn this. Exactly one is
    # set, matching `type`: course_id for lms_course_completion,
    # learning_path_id for lms_path_completion. These are also the
    # idempotency key: partial unique indexes on (user_id, course_id) and
    # (user_id, learning_path_id) are what stop a second certificate being
    # issued every time an already-finished course is re-visited — the
    # existing certs have no such guard because each has its own natural one
    # (registration_id for student_completion, payment_session_id for
    # workshop_delivery). CASCADE: deleting a course deletes its certs,
    # consistent with enrollments/progress, which also vanish with it.
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id", ondelete="CASCADE"), nullable=True)
    learning_path_id = Column(
        UUID(as_uuid=True), ForeignKey("learning_paths.id", ondelete="CASCADE"), nullable=True
    )
