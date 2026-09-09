"""Cohort knowledge-quiz domain (2026-09) — a facilitator-authored question
bank tagged by topic/difficulty/per-question timing, assembled into fixed
templates that plug into the LMS Program checklist as a new `quiz` item
type (see `services/lms/program.py`'s `AUTO_TRACKED_TYPES`).

Deliberately a separate domain from two existing, similarly-shaped tables:
- `services/lms/quiz.py` / `ItemProgress.quiz_question_order` — the
  in-course `ModuleItem.kind="quiz"` (random-N sampling from one course's
  own authored pool, unlimited retries). That's per-course practice; this
  is a per-cohort diagnostic that pulls across topics.
- `instructor_assessment` — a randomized scenario-MCQ draw for instructor
  applicants. Same question/attempt shape, different audience and a real
  behavioral difference: that domain draws N questions fresh per attempt,
  this one hands every student in a cohort the *same* fixed, hand-picked
  set (per operator decision, 2026-09) — hence a template's questions are
  an explicit ordered list (`CohortQuizTemplateQuestion`), not a draw_size/
  critical_floor config.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class CohortQuizQuestion(Base):
    """One MCQ in the facilitator-authored bank. `options` mirrors
    `AssessmentQuestion.options`/`GameQuestion.options` — a JSONB list of
    `{text, is_correct}`, exactly one correct, validated at the Pydantic
    layer. `topic` stays a free-text tag rather than a `Course` FK
    (operator decision, 2026-09) — a cohort quiz cross-cuts topics that
    don't all correspond 1:1 to a real LMS course."""

    __tablename__ = "cohort_quiz_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic = Column(String(128), nullable=False, index=True)
    subtopic = Column(String(128), nullable=True)
    # Easy|Medium|Hard — free string, not an enum: matches the source
    # question bank's own vocabulary and costs nothing to extend later.
    difficulty = Column(String(16), nullable=False)
    # Per-question countdown, shown to the student — the whole reason this
    # domain exists rather than reusing the in-course quiz (which has no
    # timing concept at all, quiz- or question-level).
    time_limit_seconds = Column(Integer, nullable=False)
    bloom_level = Column(String(32), nullable=True)
    question_type = Column(String(32), nullable=True)
    prompt = Column(Text, nullable=False)
    options = Column(JSONB, nullable=False)  # [{"text": str, "is_correct": bool}, ...]
    explanation = Column(Text, nullable=True)
    source_url = Column(String(512), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Retire, never delete (F1) — a question already drawn into a submitted
    # attempt must stay readable in that attempt's review.
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CohortQuizTemplate(Base):
    """A named, reusable fixed question set — what an LMS Program checklist
    `quiz` item actually points at (`LmsProgramItem.cohort_quiz_template_id`).
    Every student assigned that checklist item sees this exact same set
    (operator decision: "same per cohort", not a random draw)."""

    __tablename__ = "cohort_quiz_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class CohortQuizTemplateQuestion(Base):
    """One hand-picked question on a template, in authored order.
    `ondelete=SET NULL` on `question_id` (not CASCADE) — retiring a bank
    question must not silently shrink a template already handed out to a
    cohort; `CohortQuizAttempt.question_order` is what actually freezes an
    in-progress/completed attempt's real question list regardless."""

    __tablename__ = "cohort_quiz_template_questions"
    __table_args__ = (
        UniqueConstraint("template_id", "position", name="uq_cohort_quiz_template_question_position"),
        # Backstops the service-layer "already on this template" check
        # (services/lms/cohort_quiz.py::add_template_question) against a
        # genuine race — two requests adding the same question at once
        # would otherwise both pass that SELECT before either commits.
        # NULL question_id rows (a retired-and-later-hard-deleted question)
        # are exempt, same as any Postgres UNIQUE constraint.
        UniqueConstraint("template_id", "question_id", name="uq_cohort_quiz_template_question_unique"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(
        UUID(as_uuid=True), ForeignKey("cohort_quiz_templates.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    question_id = Column(UUID(as_uuid=True), ForeignKey("cohort_quiz_questions.id", ondelete="SET NULL"), nullable=True)
    position = Column(Integer, nullable=False)


class CohortQuizAttempt(Base):
    """One student's take of one checklist `quiz` item. Anchored on
    `program_item_id`, not directly on `cohort_id`/`user_id` alone — a quiz
    only ever exists behind a checklist item, unlike `instructor_assessment`
    which is opportunity-keyed. `UNIQUE(program_item_id, user_id)`: one
    attempt, no retries in v1 (this is framed as a diagnostic, not a
    pass/fail gate — see the checklist "done" hook in services/lms/
    program.py, which only checks *submitted*, never score).

    `cohort_quiz_template_id` is a frozen copy of the item's template at
    start time — an ops edit to the item's template pointer afterward
    (unusual, but possible) must not retroactively change what an
    in-progress/completed attempt is graded against.

    `question_order` is persisted at start, same reason
    `AssessmentAttempt.question_order` exists: a page refresh mid-attempt
    must never reshuffle the question or option order. Shape:
    `[{"question_id": str, "option_order": [0,2,1,3]}, ...]`, in
    presentation order."""

    __tablename__ = "cohort_quiz_attempts"
    __table_args__ = (
        UniqueConstraint("program_item_id", "user_id", name="uq_cohort_quiz_attempt_item_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_item_id = Column(
        UUID(as_uuid=True), ForeignKey("lms_program_items.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    cohort_quiz_template_id = Column(
        UUID(as_uuid=True), ForeignKey("cohort_quiz_templates.id", ondelete="RESTRICT"), nullable=False,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Denormalized from the student's LmsProgramAssignment at start time —
    # for reporting only, never re-derived.
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True)

    question_order = Column(JSONB, nullable=False)
    # in_progress|submitted
    status = Column(String(16), nullable=False, default="in_progress", server_default="in_progress")
    score = Column(Integer, nullable=True)
    total = Column(Integer, nullable=False)
    # {"<topic>": {"correct": int, "total": int}, ...} — this attempt's own
    # result only; cross-attempt strengths/weaknesses are summed live from
    # every student's submitted attempts (services/lms/cohort_quiz.py::
    # get_student_topic_breakdown), never stored as a rollup.
    topic_breakdown = Column(JSONB, nullable=True)

    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    submitted_at = Column(DateTime(timezone=True), nullable=True)


class CohortQuizAnswer(Base):
    """One answer to one question within one attempt. `selected_option_index`
    is `None` for a blank/timed-out question — the client auto-submits blank
    on a per-question timeout and advances (operator decision: timer is
    visible, timeout auto-submits blank)."""

    __tablename__ = "cohort_quiz_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_cohort_quiz_answer_attempt_question"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(
        UUID(as_uuid=True), ForeignKey("cohort_quiz_attempts.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    # SET NULL, not CASCADE — deactivating/removing a question later must
    # not erase the historical record of what was actually asked/answered.
    question_id = Column(UUID(as_uuid=True), ForeignKey("cohort_quiz_questions.id", ondelete="SET NULL"), nullable=True)
    # Denormalized at answer time so a retired/re-tagged question doesn't
    # change an already-submitted attempt's topic_breakdown.
    topic = Column(String(128), nullable=False)
    selected_option_index = Column(Integer, nullable=True)
    is_correct = Column(Boolean, nullable=False, default=False)
    timed_out = Column(Boolean, nullable=False, default=False, server_default="false")
    time_taken_seconds = Column(Integer, nullable=True)
    answered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
