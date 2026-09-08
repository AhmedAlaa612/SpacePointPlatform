import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class AssessmentConfig(Base):
    """A named, reusable instructor scenario-assessment template (e.g. "Shallow
    Flight Instructor Assessment") — one facilitator-authored question bank.

    Deliberately plural/reusable rather than a single global pool: the first
    real bank (71 Shallow-Flight-specific scenarios) is scoped to one
    curriculum, and other programs will need their own banks with their own
    categories. `AssessmentCohortAssignment` (assignment.py) is what actually
    turns a config "on" for a given cohort — a config existing here does
    nothing on its own.
    """

    __tablename__ = "assessment_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    # How many questions an attempt draws, and the floor of those that must be
    # critical-flagged — configurable per bank (2026-09) rather than the
    # platform-wide constant this started as; these two numbers are also this
    # module's defaults for a config that predates the column (see the
    # matching migration's server_default).
    draw_size = Column(Integer, nullable=False, default=15, server_default="15")
    critical_floor = Column(Integer, nullable=False, default=3, server_default="3")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AssessmentQuestion(Base):
    """One scenario-based MCQ in a config's bank. `options` mirrors
    `GameQuestion.options` (`models/games/game.py`) — a JSONB list of
    `{text, is_correct}`, validated as "exactly one correct option" at the
    Pydantic layer, not here.

    `category` and `critical` are the two fields neither the Live Games nor
    the LMS quiz question models have — category-balanced sampling and a
    critical-question floor are this domain's entire reason for not just
    reusing one of those.
    """

    __tablename__ = "assessment_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id = Column(
        UUID(as_uuid=True), ForeignKey("assessment_configs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category = Column(String(128), nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    options = Column(JSONB, nullable=False)  # [{"text": str, "is_correct": bool}, ...]
    critical = Column(Boolean, nullable=False, default=False, server_default="false")
    rationale = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
