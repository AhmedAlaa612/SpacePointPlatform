"""Live games — per-session assignment + snapshot copy (Live Games Phase
2C, 8-4; D11, D12).

`GameSessionAssignment` attaches a `Game` template to one `Session` with an
instructor-facing note (never shown to students). Its config
(`time_limit_seconds`/`floor_pct`/`blackout_count`) is copied from the
template's defaults at assign time, then independently editable — same
"copy, don't reference" precedent as `DesignComponent` copying
`DesignComponentLibrary` (`models/missions/design.py`).

`GameSessionQuestion` is the assignment's own snapshot of `GameQuestion`
rows, copied field-by-field at assign time. It carries no FK back to
`game_questions` — editing this copy (including mid-game, 8-7) never
touches the shared template or any other session's copy of the same game.
`game_id` on the assignment is RESTRICT, not CASCADE: retiring a template
must never silently corrupt a session that already has its own copy.

One session can carry several assignments (a session might run two
different games at different points) — no uniqueness constraint on
(session_id, game_id).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class GameSessionAssignment(Base):
    __tablename__ = "game_session_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="RESTRICT"), nullable=False)
    # Instructor-facing only — never surfaced to students (D11).
    instructor_note = Column(Text, nullable=True)
    # Copied from Game.default_* at assign time; independently editable after.
    time_limit_seconds = Column(Integer, nullable=False)
    floor_pct = Column(Integer, nullable=False)
    blackout_count = Column(Integer, nullable=False)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class GameSessionQuestion(Base):
    __tablename__ = "game_session_questions"
    __table_args__ = (
        UniqueConstraint("assignment_id", "position", name="uq_game_session_questions_assignment_position"),
        CheckConstraint("points_mode IN ('normal', 'double')", name="ck_game_session_questions_points_mode"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("game_session_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False)
    prompt = Column(Text, nullable=False)
    options = Column(JSONB, nullable=False)
    time_limit_seconds = Column(Integer, nullable=True)
    points_mode = Column(String(8), nullable=False, default="normal", server_default="normal")
