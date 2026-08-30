import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class CohortCallInterest(Base):
    """An instructor's answer to one cohort-wide call: the role they want, the
    days they can do, and what support they'd need — stated **once for the
    cohort** rather than repeated on every session.

    Registering still writes the per-session `InstructorInterest` rows for the
    ticked sessions, so everything already built on them keeps working with no
    changes at all: `list_eligible_instructors`, `openings_for_session`'s
    waitlist count, and `select_instructors`' `without_interest` flag. This row
    holds the parts that are *about the cohort*, which duplicating five times
    would only make inconsistent — a cover letter, one role choice, and the
    support answers the operations process doc (§2) asks for.

    The support flags are deliberately three booleans plus free text rather
    than a generic questionnaire: §2 names exactly these, and
    `applicant_profiles.deliver_city_ids` already answers "would you travel
    here?" from the profile side (surfaced by `list_eligible_instructors`'s
    `available_in_city`). `travelling_from_other_city` is the instructor
    telling ops it applies *to this booking*, which is the thing that triggers
    a transport/accommodation review.

    `cohort_id` is denormalised from `CohortCall.cohort_id` purely so lookups
    don't need a join — the same reasoning `CohortCallTarget.cohort_id` and
    `SessionCallTarget.session_id` already use.
    """

    __tablename__ = "cohort_call_interests"
    __table_args__ = (
        UniqueConstraint("cohort_call_id", "user_id", name="uq_cohort_call_interest"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_call_id = Column(
        UUID(as_uuid=True), ForeignKey("cohort_calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # SET NULL, not CASCADE — a role being retired must not erase the record
    # of who applied for it. Same choice as InstructorInterest.role_id.
    role_id = Column(UUID(as_uuid=True), ForeignKey("delivery_roles.id", ondelete="SET NULL"), nullable=True)

    # The cover letter — "why you'd like this one".
    note = Column(Text, nullable=True)

    # Operations process doc §2.
    needs_transport = Column(Boolean, nullable=False, default=False, server_default="false")
    needs_ops_support = Column(Boolean, nullable=False, default=False, server_default="false")
    travelling_from_other_city = Column(Boolean, nullable=False, default=False, server_default="false")
    concerns = Column(Text, nullable=True)

    # I5-5, mirrored from InstructorInterest: *when* they agreed and to *which*
    # version of the combined role + general responsibilities text, so a later
    # edit cannot retroactively change what was accepted.
    responsibilities_accepted_at = Column(DateTime(timezone=True), nullable=True)
    responsibilities_version = Column(String(32), nullable=True)

    # open|selected|withdrawn — the applicant's own state in this call, kept
    # separate from whether they ended up with a CohortInstructorAssignment so
    # "applied and was never picked" stays queryable.
    status = Column(String(16), nullable=False, default="open", server_default="open")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
