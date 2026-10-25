import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class PreSessionQuizQuestion(Base):
    """A question in the facilitator-authored Pre-Session Quiz Bank.

    Supports two question types:
    - `pinout_table`: Interactive hardware connector table where cells are clickable
      and the instructor selects 1 or more cells per pin row (or flags a datasheet error via "Other").
    - `mcq`: Standard multiple-choice / jumper selection (e.g. Leave Open vs Short),
      with optional "Other" text explanation.

    Both question and explanation support optional images (`image_url`, `explanation_image_url`),
    and the explanation can also include a reference/corrected connector table (`explanation_table`).
    """

    __tablename__ = "pre_session_quiz_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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

    explanation = Column(Text, nullable=True)
    explanation_image_url = Column(String(512), nullable=True)
    # Optional second connector table displayed in the post-submission explanation
    explanation_table = Column(JSONB, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PreSessionQuizPreset(Base):
    """A reusable Pre-Session Quiz template/preset assembled from questions in the bank,
    with optional reference datasheet links/documents."""

    __tablename__ = "pre_session_quiz_presets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # Ordered list of question UUID strings
    question_ids = Column(JSONB, nullable=False, default=list, server_default="[]")
    # Optional reference documents/links shown at the top of the quiz
    # [{"id": str, "title": str, "url": str, "is_file": bool}]
    reference_attachments = Column(JSONB, nullable=False, default=list, server_default="[]")
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
    """An instructor's completed pre-session quiz attempt for a session."""

    __tablename__ = "pre_session_quiz_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    preset_id = Column(
        UUID(as_uuid=True), ForeignKey("pre_session_quiz_presets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Per-question answer records:
    # [
    #   {
    #     "question_id": str,
    #     "selected_option_index": int | None,
    #     "selected_cells": [[int, ...], ...] | None,
    #     "chose_other": bool,
    #     "other_text": str | None,
    #     "status": "correct" | "incorrect" | "pending_review",
    #     "reviewed_by": str | None,
    #     "reviewed_at": str | None,
    #     "review_comment": str | None
    #   }
    # ]
    answers = Column(JSONB, nullable=False, default=list, server_default="[]")

    auto_score = Column(Integer, nullable=False, default=0, server_default="0")
    final_score = Column(Integer, nullable=False, default=0, server_default="0")
    total_questions = Column(Integer, nullable=False, default=0, server_default="0")
    pending_review_count = Column(Integer, nullable=False, default=0, server_default="0")

    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
