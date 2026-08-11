"""Live games — the authored template (Live Games Phase 2C, 8-3).

`Game`/`GameQuestion` are the reusable template a facilitator builds once
(D4) — same template/instance split `Mission`/`MissionVariant` already
uses. Nothing here is session-, run-, or attempt-shaped; that starts at
`GameSessionAssignment` (8-4), which snapshots this template's questions
into its own independently-editable copy rather than referencing it live
(D12) — editing a session's copy, including mid-game (8-7), never touches
this table or any other session's copy of the same game.

`GameQuestion.points_mode` is `normal`|`double` (D8, corrected from an
earlier free-number design) — `services/games/points.py` is the single
place that number becomes 100 or 200.
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


class Game(Base):
    __tablename__ = "games"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    # Defaults only — copied onto a GameSessionAssignment's own config at
    # assign time (8-4), then independently editable there. Changing a
    # default here never retroactively touches an already-assigned session.
    default_time_limit_seconds = Column(Integer, nullable=False, default=20, server_default="20")
    default_floor_pct = Column(Integer, nullable=False, default=25, server_default="25")
    default_blackout_count = Column(Integer, nullable=False, default=3, server_default="3")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class GameQuestion(Base):
    __tablename__ = "game_questions"
    __table_args__ = (
        UniqueConstraint("game_id", "position", name="uq_game_questions_game_position"),
        CheckConstraint("points_mode IN ('normal', 'double')", name="ck_game_questions_points_mode"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    position = Column(Integer, nullable=False)
    prompt = Column(Text, nullable=False)
    # [{"text": str, "is_correct": bool}, ...] — same shape LMS quiz options
    # already use, exactly-one-correct validated at the schema layer.
    options = Column(JSONB, nullable=False)
    # NULL = use the game's default_time_limit_seconds.
    time_limit_seconds = Column(Integer, nullable=True)
    points_mode = Column(String(8), nullable=False, default="normal", server_default="normal")
