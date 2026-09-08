import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base

# Fixed platform-wide dimensions — not admin-configurable, unlike Competition
# Judging's per-competition rubric criteria (`models/competitions/judging.py`):
# the boss's spec names exactly these 10 for every instructor everywhere, so a
# `RatingCriterion` table would be unused flexibility. `dimension_scores` on
# InstructorProgramRating is keyed by these.
RATING_DIMENSIONS = [
    "punctuality",
    "technical_knowledge",
    "teaching_facilitation",
    "student_engagement",
    "communication",
    "commitment_reliability",
    "teamwork_collaboration",
    "safety_procedure_compliance",
    "problem_solving_adaptability",
    "documentation_operational_discipline",
]


class InstructorProgramRating(Base):
    """One Project Lead's post-program rating of one instructor, for one
    cohort delivery — once per (cohort, instructor, rater), not once per
    session-day even on a multi-day camp (operator decision).

    `dimension_scores` is `{key: 1-5}` for each of `RATING_DIMENSIONS` above,
    validated at the Pydantic layer. Overall rating is the average of these,
    computed at read time wherever it's shown
    (`services/instructor_assessment/performance.py`) — never stored, same
    "derive, never cache" convention every other leaderboard/aggregate in
    this codebase follows.

    `recommended` and `flag` are reported/visible only — a badge on the
    profile and the selection screen — and deliberately do not move the
    numeric Priority Score (operator decision): a "Concern" flag must stay
    visible next to a decent-looking average, not get quietly blended away.

    `submitted` ratchets forward only, same shape as `CompetitionScore.submitted`
    (`models/competitions/judging.py`) — autosave keeps updating a draft row
    until the rater deliberately submits; a submitted rating is never
    reopened by revisiting the form.
    """

    __tablename__ = "instructor_program_ratings"
    __table_args__ = (
        UniqueConstraint(
            "cohort_id", "instructor_user_id", "rater_user_id",
            name="uq_instructor_program_rating_cohort_instructor_rater",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True)
    instructor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rater_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    dimension_scores = Column(JSONB, nullable=False, default=dict)
    strengths = Column(Text, nullable=True)
    areas_for_improvement = Column(Text, nullable=True)
    recommended = Column(Boolean, nullable=True)
    # none|exceptional|concern
    flag = Column(String(16), nullable=False, default="none", server_default="none")
    submitted = Column(Boolean, nullable=False, default=False, server_default="false")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    submitted_at = Column(DateTime(timezone=True), nullable=True)


class InstructorCertificationTag(Base):
    """A free-text certification/qualification tag on an instructor's
    profile — "Certified: Advanced Safety". Deliberately no issuer/expiry/
    verification workflow: nothing concrete to design against yet (the
    boss's spec says "if applicable" with no named certifications), so this
    is a placeholder until real ones are named."""

    __tablename__ = "instructor_certification_tags"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
