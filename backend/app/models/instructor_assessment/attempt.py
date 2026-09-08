import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class AssessmentAttempt(Base):
    """One instructor's draw of 15 questions for one specific opportunity.

    Anchored on `cohort_call_id` (`sessions.cohort_calls`), not on
    `InstructorInterest`/`CohortCallInterest` directly: every open call —
    even a lone single-session one — already belongs to a `CohortCall`
    (`services/sessions/staffing.py::_find_or_create_open_cohort_call`), so
    this one FK covers both the direct-session-interest path and the
    cohort-wide path with a single gate check instead of two. Unique on
    (cohort_call_id, user_id) — one attempt per opportunity ("For each
    application/session, the system should randomly select 15 questions"),
    not a standing quiz reused across applications.

    `question_order` is the drawn set, persisted at draw time — get-or-create
    semantics, same reason the LMS quiz's `quiz_question_order` exists
    (`models/lms/enrollment.py`): a page refresh mid-attempt must not
    reshuffle the questions or the answer options out from under the
    instructor. Shape: `[{"question_id": str, "option_order": [0,2,1,3]}, ...]`,
    in presentation order — `option_order` is which original option index
    shows at each displayed position, so the correct answer is never
    inferable from letter position alone.
    """

    __tablename__ = "assessment_attempts"
    __table_args__ = (
        UniqueConstraint("cohort_call_id", "user_id", name="uq_assessment_attempt_call_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    config_id = Column(UUID(as_uuid=True), ForeignKey("assessment_configs.id", ondelete="RESTRICT"), nullable=False)
    cohort_call_id = Column(
        UUID(as_uuid=True), ForeignKey("cohort_calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    question_order = Column(JSONB, nullable=False)
    # in_progress|submitted
    status = Column(String(16), nullable=False, default="in_progress", server_default="in_progress")
    score = Column(Integer, nullable=True)
    total = Column(Integer, nullable=False, default=15, server_default="15")
    critical_correct = Column(Integer, nullable=True)
    critical_total = Column(Integer, nullable=True)
    # {"<category>": {"correct": int, "total": int}, ...} — this attempt's own
    # draw only, not a running total (see services/instructor_assessment/
    # performance.py for the cross-attempt history, computed live, never
    # stored).
    category_breakdown = Column(JSONB, nullable=True)

    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    submitted_at = Column(DateTime(timezone=True), nullable=True)


class AssessmentAnswer(Base):
    """One instructor's answer to one question within one attempt — same
    shape as `GameAnswer` (`models/games/run.py`)."""

    __tablename__ = "assessment_answers"
    __table_args__ = (
        UniqueConstraint("attempt_id", "question_id", name="uq_assessment_answer_attempt_question"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(
        UUID(as_uuid=True), ForeignKey("assessment_attempts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SET NULL, not CASCADE — deactivating/removing a question later must not
    # erase the historical record of what was actually asked and answered.
    question_id = Column(UUID(as_uuid=True), ForeignKey("assessment_questions.id", ondelete="SET NULL"), nullable=True)
    selected_option_index = Column(Integer, nullable=True)
    is_correct = Column(Boolean, nullable=False, default=False)
    answered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
