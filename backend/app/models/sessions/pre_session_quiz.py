import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class PreSessionQuizQuestion(Base):
    """A question in the facilitator-authored Pre-Session Quiz Bank.

    Supports four question types:
    - `pinout_table`: Interactive hardware connector table where cells are clickable
      and the instructor selects 1 or more cells per pin row (or flags a datasheet error via "Other").
    - `mcq`: Standard multiple-choice / jumper selection (e.g. Leave Open vs Short),
      with optional "Other" text explanation.
    - `written`: Open-ended technical answer reviewed by Ops.
    - `subsystem_matching`: Inline or reusable subsystem classification matching.

    Both question and explanation support optional images (`image_url`, `explanation_image_url`),
    and the explanation can also include a reference/corrected connector table (`explanation_table`).
    """

    __tablename__ = "pre_session_quiz_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(64), nullable=True, index=True)
    topic = Column(String(128), nullable=False, default="General", server_default="General", index=True)
    question_type = Column(String(32), nullable=False, default="pinout_table", server_default="pinout_table")
    title = Column(String(255), nullable=False)
    prompt = Column(Text, nullable=False)
    image_url = Column(String(512), nullable=True)

    # For `mcq`: [{"text": str, "is_correct": bool}, ...]
    options = Column(JSONB, nullable=False, default=list, server_default="[]")

    # For `pinout_table`:
    # {
    #   "connector_name": "J6",
    #   "header_subtitle": "J61, J62, J63, J64, J65, J66",
    #   "columns": ["1", "2", "3"],
    #   "rows": [
    #     {"label": "Pin 1", "cells": [{"text": "3V3", "is_correct": true}, {"text": "Main", "is_correct": true}, {"text": "GND", "is_correct": false}]}
    #   ]
    # }
    table_config = Column(JSONB, nullable=True)

    # Whether the question displays an "Other (explain)" option
    allow_other = Column(Boolean, nullable=False, default=False, server_default="false")
    # Whether "Other" is the expected path (e.g. tricky datasheet error question like Connector J6)
    is_other_correct = Column(Boolean, nullable=False, default=False, server_default="false")

    # Critical question flag (e.g. safety-critical questions with mandatory passing thresholds)
    critical = Column(Boolean, nullable=False, default=False, server_default="false", index=True)
    # Scoring points / weight
    points = Column(Integer, nullable=False, default=1, server_default="1")

    explanation = Column(Text, nullable=True)
    explanation_image_url = Column(String(512), nullable=True)
    # Optional second connector table displayed in the post-submission explanation
    explanation_table = Column(JSONB, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PreSessionQuizDatasheet(Base):
    """A technical datasheet or reference document in the centralized Datasheet Library.
    Can be attached to multiple readiness pipeline presets across cohorts and programs.
    """

    __tablename__ = "pre_session_quiz_datasheets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    url = Column(String(512), nullable=False)
    doc_type = Column(String(64), nullable=False, default="datasheet", server_default="datasheet")
    subsystem_tag = Column(String(64), nullable=True, index=True)
    description = Column(Text, nullable=True)
    image_url = Column(String(512), nullable=True)
    page_count = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class PreSessionQuizPreset(Base):
    """A reusable Pre-Session Quiz template/preset assembled from questions in the bank,
    with optional reference datasheet links/documents and ordered pipeline phases."""

    __tablename__ = "pre_session_quiz_presets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Preset usage type: "readiness_pipeline" | "pre_assessment" | "universal"
    preset_type = Column(String(32), nullable=False, default="readiness_pipeline", server_default="readiness_pipeline", index=True)

    # Pre-Assessment draw rules (when used for applicant screening)
    draw_size = Column(Integer, nullable=True, default=15, server_default="15")
    critical_floor = Column(Integer, nullable=True, default=3, server_default="3")
    passing_score_percent = Column(Integer, nullable=True, default=80, server_default="80")

    # Legacy flat question list kept synced with quiz phases for backward compatibility
    question_ids = Column(JSONB, nullable=False, default=list, server_default="[]")

    # Datasheet & User Guide Catalog:
    # [{"id": str, "title": str, "url": str, "doc_type": "datasheet" | "user_guide", "subsystem_tag": str | None, "image_url": str | None, "is_file": bool}]
    reference_attachments = Column(JSONB, nullable=False, default=list, server_default="[]")

    # Ordered Pipeline Phases:
    # [{"id": str, "phase_type": "explore_datasheets" | "subsystem_matching" | "quiz", "title": str, ...}]
    phases = Column(JSONB, nullable=False, default=list, server_default="[]")

    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PreSessionQuizAssignment(Base):
    """Assigns a Pre-Session Quiz Preset at the Program, Cohort, or Session level.
    Follows the 3-level inheritance hierarchy (Session overrides Cohort overrides Program).
    If `preset_id` is None at a lower level, it explicitly disables the inherited quiz for that scope."""

    __tablename__ = "pre_session_quiz_assignments"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_pre_session_quiz_assignment_one_owner",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(UUID(as_uuid=True), ForeignKey("programs.id", ondelete="CASCADE"), nullable=True, index=True)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True, index=True)

    preset_id = Column(
        UUID(as_uuid=True), ForeignKey("pre_session_quiz_presets.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PreSessionQuizAttempt(Base):
    """An instructor's cohort-level readiness pipeline state and rollup metrics."""

    __tablename__ = "pre_session_quiz_attempts"
    __table_args__ = (
        UniqueConstraint("cohort_id", "user_id", name="uq_pre_session_quiz_attempt_cohort_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True)
    # Nullable session_id retained for legacy FK / reference links
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True)
    preset_id = Column(
        UUID(as_uuid=True), ForeignKey("pre_session_quiz_presets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Pipeline State Machine
    # status: "in_progress" | "cooldown_locked" | "completed"
    status = Column(String(32), nullable=False, default="in_progress", server_default="in_progress")
    current_phase_index = Column(Integer, nullable=False, default=0, server_default="0")
    phase_started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    locked_until = Column(DateTime(timezone=True), nullable=True)

    # Timing & Score Rollups
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    total_duration_seconds = Column(Integer, nullable=False, default=0, server_default="0")

    # Latest passing (or latest submitted) answers across all quiz questions for Ops quick review
    answers = Column(JSONB, nullable=False, default=list, server_default="[]")
    # Latest per-phase summary: {phase_id: {passed, best_score_pct, trials_count, total_duration_seconds, last_trial_id}}
    phase_states = Column(JSONB, nullable=False, default=dict, server_default="{}")

    auto_score = Column(Integer, nullable=False, default=0, server_default="0")
    final_score = Column(Integer, nullable=False, default=0, server_default="0")
    total_questions = Column(Integer, nullable=False, default=0, server_default="0")
    pending_review_count = Column(Integer, nullable=False, default=0, server_default="0")


class PreSessionQuizPhaseTrial(Base):
    """Append-only record of a single submission/trial for a specific phase in the pipeline."""

    __tablename__ = "pre_session_quiz_phase_trials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pre_session_quiz_attempts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase_id = Column(String(64), nullable=False, index=True)
    phase_index = Column(Integer, nullable=False)
    phase_type = Column(String(32), nullable=False)
    trial_number = Column(Integer, nullable=False, default=1)

    started_at = Column(DateTime(timezone=True), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    duration_seconds = Column(Integer, nullable=False, default=0)

    score = Column(Integer, nullable=False, default=0)
    total = Column(Integer, nullable=False, default=0)
    score_pct = Column(Integer, nullable=False, default=100)
    pass_percentage_required = Column(Integer, nullable=False, default=100)
    passed = Column(Boolean, nullable=False, default=False)
    cooldown_until = Column(DateTime(timezone=True), nullable=True)

    # Snapshot of submitted answers + per-item grading status for this trial
    payload = Column(JSONB, nullable=False, default=dict, server_default="{}")
