"""Pydantic schemas for the Program model (V2 R2-3 — registration desk).

Mirrors app/models/sessions/program.py field-for-field. No dedicated
programs service module exists yet — CRUD lives directly in
routers/sessions/programs.py, matching the established convention for
simple CRUD elsewhere in this codebase (e.g. routers/instructors/admin.py's
invitation-code endpoints).
"""

from __future__ import annotations

from datetime import datetime, time
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ProgramType = Literal["workshop", "course", "info_session", "competition"]
PricingModel = Literal["paid", "free"]
# "percentage": completion_rule_value is 0-100, compared against a cohort's
# present/total_sessions rate. "session_count": completion_rule_value is a
# whole number of sessions the student must be marked present for.
CompletionRuleType = Literal["percentage", "session_count"]


class ProgramBase(BaseModel):
    name: str
    program_type: ProgramType
    pricing_model: PricingModel
    description: str | None = None
    price: Decimal | None = None
    duration_hours: Decimal | None = None
    default_capacity: int | None = None
    active: bool = True
    completion_rule_type: CompletionRuleType = "percentage"
    completion_rule_value: Decimal = Decimal("70")
    poster_template_url: str | None = None
    # Instructor-assessment default (2026-09) — copied once into a new
    # cohort's own AssessmentCohortAssignment at creation (create_cohort),
    # never read live afterwards. See Program.default_assessment_config_id's
    # docstring.
    default_assessment_config_id: UUID | None = None
    default_certificate_template_id: UUID | None = None
    keep_course_access_after_completion: bool = True


class ProgramCreate(ProgramBase):
    # Format like SATKIT-WS-2026-Q3 (see the model's own comment: "validated
    # in the service layer, not the DB"). No format regex is enforced here —
    # only non-emptiness, via the plain `str` type — since no spec for the
    # exact validation rule was given; a stricter check can be added once one is.
    code: str


class ProgramUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    program_type: ProgramType | None = None
    pricing_model: PricingModel | None = None
    description: str | None = None
    price: Decimal | None = None
    duration_hours: Decimal | None = None
    default_capacity: int | None = None
    active: bool | None = None
    completion_rule_type: CompletionRuleType | None = None
    completion_rule_value: Decimal | None = None
    poster_template_url: str | None = None
    default_assessment_config_id: UUID | None = None
    default_certificate_template_id: UUID | None = None
    keep_course_access_after_completion: bool | None = None


class ProgramOut(ProgramBase):
    id: UUID
    code: str
    created_at: datetime
    # Competition domain (2026-08-24) — read-only, derived from
    # `program_type == "competition"` (see the model's `is_competition`
    # property). Not settable here: `program_type` is the single lever.
    is_competition: bool

    class Config:
        from_attributes = True


ProgramCloneCarryBucket = Literal[
    "roles",  # ProgramOpening rows
    "checklist",  # LmsProgram + LmsProgramItem rows
    "materials",  # session_materials (program_id)
    "assessment",  # default_assessment_config_id
    "certificate",  # default_certificate_template_id
    "rubric",  # CompetitionRubric + CompetitionRubricCriterion (if competition)
]


class ProgramCloneRequest(BaseModel):
    name: str
    code: str
    carry: list[ProgramCloneCarryBucket] = Field(
        default_factory=lambda: ["roles", "checklist", "materials", "assessment", "certificate", "rubric"]
    )


VariationCarryBucket = Literal[
    "days",  # ProgramVariationDay rows + day/variation delivery checklists
    "roles",  # ProgramOpening rows (role rates & slots)
    "pre_quiz",  # PreSessionQuizAssignment rows (variation & variation_day)
    "lms",  # LmsProgramItem rows (owner_type="variation")
    "component_config",  # DesignComponentConfig (owner_type="variation")
    "hints",  # CohortHintChallenge (owner_type="variation")
    "materials",  # SessionMaterial (variation_id)
    "assessment",  # default_assessment_config_id
    "certificate",  # default_certificate_template_id & default_team_certificate_template_id
    "rubric",  # CompetitionRubric + CompetitionRubricCriterion
    "scalars",  # duration_hours, default_capacity, pricing, completion_rule, poster, keep_access
]


class ProgramVariationDayCreate(BaseModel):
    day_number: int | None = None
    title: str | None = None
    duration_hours: Decimal | None = None
    starts_at: time | None = None


class ProgramVariationDayUpdate(BaseModel):
    day_number: int | None = None
    title: str | None = None
    duration_hours: Decimal | None = None
    starts_at: time | None = None


class ProgramVariationDayOut(BaseModel):
    id: UUID
    variation_id: UUID
    day_number: int
    title: str | None = None
    duration_hours: Decimal | None = None
    starts_at: time | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ProgramVariationDaysReorderIn(BaseModel):
    day_ids: list[UUID]


class ProgramVariationBase(BaseModel):
    name: str
    description: str | None = None
    is_default: bool = False
    is_active: bool = True
    sort_order: int = 1
    duration_hours: Decimal | None = None
    default_capacity: int | None = None
    poster_template_url: str | None = None
    keep_course_access_after_completion: bool | None = None
    pricing_model: PricingModel | None = None
    price: Decimal | None = None
    completion_rule_type: CompletionRuleType | None = None
    completion_rule_value: Decimal | None = None
    default_assessment_config_id: UUID | None = None
    default_certificate_template_id: UUID | None = None
    default_team_certificate_template_id: UUID | None = None


class ProgramVariationCreate(ProgramVariationBase):
    mode: Literal["blank", "duplicate", "from_cohort"] = "blank"
    source_variation_id: UUID | None = None
    source_cohort_id: UUID | None = None
    carry: list[VariationCarryBucket] = Field(
        default_factory=lambda: [
            "days",
            "roles",
            "pre_quiz",
            "lms",
            "component_config",
            "hints",
            "materials",
            "assessment",
            "certificate",
            "rubric",
            "scalars",
        ]
    )


class ProgramVariationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_default: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None
    duration_hours: Decimal | None = None
    default_capacity: int | None = None
    poster_template_url: str | None = None
    keep_course_access_after_completion: bool | None = None
    pricing_model: PricingModel | None = None
    price: Decimal | None = None
    completion_rule_type: CompletionRuleType | None = None
    completion_rule_value: Decimal | None = None
    default_assessment_config_id: UUID | None = None
    default_certificate_template_id: UUID | None = None
    default_team_certificate_template_id: UUID | None = None


class ProgramVariationOut(ProgramVariationBase):
    id: UUID
    program_id: UUID
    created_at: datetime
    days: list[ProgramVariationDayOut] = []
    days_count: int = 0
    cohorts_count: int = 0

    class Config:
        from_attributes = True
