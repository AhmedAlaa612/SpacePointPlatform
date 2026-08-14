"""Live games — one live play-through (Live Games Phase 2C, 8-6; D8, D14,
D15, D16, D17).

`GameRun` is one instructor "Start" — `run_no` increments per
`assignment_id` on every restart (D15: "keep it one run, restart for
all"), so a restart is a **new row**, never a wipe of the old one. The
old run's rows stay exactly as they were played; 8-9's restart handler
reverses its point_events (new offsetting entries, D17) without ever
touching these rows. Status is `lobby` (joinable, not started) →
`live` (`current_question_position` tracks which question is up) →
`ended`.

`GameParticipant` snapshots the student's nickname at join time —
nicknames can be rerolled (D2) independently of any run in progress, so
a run's own roster/leaderboard should never silently relabel mid-game.

`GameAnswer` is one row per (participant, question) — `question_id` is
`SET NULL`, not `RESTRICT`, because D13 allows deleting an
already-answered question mid-game; that delete must never be blocked
by its own answer history, and 8-9 reverses the affected rows' points
*before* the question is actually removed (see `reversed_at`).

No denormalized running-score column anywhere on this table (or on
`GameParticipant`) — same "derived, never cached" convention
`services/lms/leaderboard.py` already commits to for the platform
leaderboard: a run's standings are `SUM(points_awarded) WHERE
reversed_at IS NULL`, computed at read time (`services/games/runs.py
::run_leaderboard`), so a reversal (8-9) is reflected for free with no
second place to update.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class GameRun(Base):
    __tablename__ = "game_runs"
    __table_args__ = (
        UniqueConstraint("assignment_id", "run_no", name="uq_game_runs_assignment_run_no"),
        CheckConstraint("status IN ('lobby', 'live', 'ended')", name="ck_game_runs_status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("game_session_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    run_no = Column(Integer, nullable=False)
    # How many times this run has been restarted. A restart resets the run
    # in place (same row, same join code, same participants) rather than
    # creating a new one, so this is what keeps a replayed question's points
    # ledger key distinct from the reversed one before it.
    restart_no = Column(Integer, nullable=False, default=0, server_default="0")
    status = Column(String(16), nullable=False, default="lobby", server_default="lobby")
    # NULL while lobby/ended; 1..N (a GameSessionQuestion.position) while live.
    current_question_position = Column(Integer, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class GameParticipant(Base):
    __tablename__ = "game_participants"
    __table_args__ = (
        UniqueConstraint("run_id", "user_id", name="uq_game_participants_run_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("game_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    nickname_snapshot = Column(String(64), nullable=False)
    # NULL = use the profile photo (D18's default); a character key otherwise.
    avatar = Column(String(64), nullable=True)
    joined_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class GameAnswer(Base):
    __tablename__ = "game_answers"
    # A participant may answer a question only once *that still counts*. The
    # constraint is partial rather than absolute because a restart resets the
    # run in place: the previous attempt's rows stay as history with
    # `reversed_at` set, and the replay writes a fresh row alongside them.
    __table_args__ = (
        Index(
            "uq_game_answers_participant_question",
            "participant_id", "question_id",
            unique=True, postgresql_where=text("reversed_at IS NULL"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participant_id = Column(UUID(as_uuid=True), ForeignKey("game_participants.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id = Column(UUID(as_uuid=True), ForeignKey("game_session_questions.id", ondelete="SET NULL"), nullable=True)
    # NULL = no answer submitted (timed out).
    selected_option_index = Column(Integer, nullable=True)
    is_correct = Column(Boolean, nullable=False, default=False)
    elapsed_seconds = Column(Numeric(6, 2), nullable=True)
    points_awarded = Column(Integer, nullable=False, default=0)
    # 8-9's marker — set (never deleted) when this row's point_events
    # contribution has been reversed, either by a full restart (D15) or a
    # mid-game question delete (D16).
    reversed_at = Column(DateTime(timezone=True), nullable=True)
    answered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
