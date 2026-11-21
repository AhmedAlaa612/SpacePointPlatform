import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ProgramVariation(Base):
    """A delivery format / variant of a Program (e.g. '4-Day Full' vs
    '3-Day Express' for Shallow Flight).

    Follows the sparse-override pattern: scalar/config fields on this row are
    nullable, and NULL means 'inherit from the parent Program'. Days, delivery
    checklists, pre-session quizzes, role openings, LMS checklist items,
    component configs, hint stations, materials, and rubrics can all be
    customized per variation.
    """

    __tablename__ = "program_variations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(
        UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_default = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    sort_order = Column(Integer, nullable=False, default=1, server_default="1")

    # Nullable overrides — NULL inherits from parent Program
    duration_hours = Column(Numeric(5, 2), nullable=True)
    default_capacity = Column(Integer, nullable=True)
    poster_template_url = Column(String(512), nullable=True)
    keep_course_access_after_completion = Column(Boolean, nullable=True)
    pricing_model = Column(String(24), nullable=True)
    price = Column(Numeric(10, 2), nullable=True)
    completion_rule_type = Column(String(16), nullable=True)
    completion_rule_value = Column(Numeric(6, 2), nullable=True)
    default_assessment_config_id = Column(
        UUID(as_uuid=True), ForeignKey("assessment_configs.id", ondelete="SET NULL"), nullable=True,
    )
    default_certificate_template_id = Column(
        UUID(as_uuid=True), ForeignKey("program_certificate_templates.id", ondelete="SET NULL"), nullable=True,
    )
    default_team_certificate_template_id = Column(
        UUID(as_uuid=True), ForeignKey("program_certificate_templates.id", ondelete="SET NULL"), nullable=True,
    )

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ProgramVariationDay(Base):
    """One template day inside a ProgramVariation (Day 1..N).

    Replaces the legacy hidden '[Template] ...' draft Cohort + fake-dated
    Session rows with an explicit integer `day_number`.
    """

    __tablename__ = "program_variation_days"
    __table_args__ = (
        UniqueConstraint("variation_id", "day_number", name="uq_program_variation_day_number"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    variation_id = Column(
        UUID(as_uuid=True), ForeignKey("program_variations.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    day_number = Column(Integer, nullable=False)
    title = Column(String(256), nullable=True)
    duration_hours = Column(Numeric(5, 2), nullable=True)
    starts_at = Column(Time, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
