"""Pydantic schemas for the Program model (V2 R2-3 — registration desk).

Mirrors app/models/sessions/program.py field-for-field. No dedicated
programs service module exists yet — CRUD lives directly in
routers/sessions/programs.py, matching the established convention for
simple CRUD elsewhere in this codebase (e.g. routers/instructors/admin.py's
invitation-code endpoints).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

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
    default_capacity: int | None = None
    active: bool | None = None
    completion_rule_type: CompletionRuleType | None = None
    completion_rule_value: Decimal | None = None
    poster_template_url: str | None = None
    default_assessment_config_id: UUID | None = None


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
