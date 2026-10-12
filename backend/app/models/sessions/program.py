import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
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
    program_type = Column(String(24), nullable=False)  # workshop|course|info_session|competition
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
    # Ops-set master poster template link — cohorts inherit this unless overridden
    poster_template_url = Column(String(512), nullable=True)
    # Instructor-assessment default (2026-09) — same copy-not-inherit shape as
    # `ProgramOpening`: `create_cohort` seeds a brand-new cohort's own
    # `AssessmentCohortAssignment` from this the moment it's created, once,
    # and never again. Editing this afterwards never reaches back into a
    # cohort that already exists; ops overrides the seeded copy per-cohort
    # from the cohort's own Assessment tab (`AssessmentCohortAssignment`),
    # same place that's always lived. SET NULL rather than RESTRICT on
    # delete — unlike an active `AssessmentCohortAssignment`, this is just a
    # template pointer for cohorts not yet created, not a live gate, so
    # deleting the config it points at should just clear the default rather
    # than being blocked.
    default_assessment_config_id = Column(
        UUID(as_uuid=True), ForeignKey("assessment_configs.id", ondelete="SET NULL"), nullable=True,
    )
    # Default certificate template (2026-09) — overrides built-in dark/light default
    default_certificate_template_id = Column(
        UUID(as_uuid=True),
        ForeignKey(
            "program_certificate_templates.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_programs_default_certificate_template_id",
        ),
        nullable=True,
    )
    keep_course_access_after_completion = Column(
        Boolean, nullable=False, default=True, server_default="true",
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    @property
    def is_competition(self) -> bool:
        """Competition domain (2026-08-24, Ru'ya Space Race first) reads
        this everywhere rather than a `program_type == "competition"`
        string comparison sprinkled across services/routers. `competition`
        is a normal `program_type` value (like `workshop`/`course`), not a
        separate boolean flag — a competition doesn't need a second format
        axis, it just needs judging (rubric/scores/publish), temporary
        judge accounts, and team-scoped checklist items unlocked, which
        this property's callers key off of. See services/competitions/."""
        return self.program_type == "competition"
