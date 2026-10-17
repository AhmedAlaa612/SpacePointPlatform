"""Arcade Games domain — standalone interactive mini-games and simulations
from SpacePoint Mission Arcade that can be played freely in `/learn/arcade`
or attached to an LMS Program checklist (`LmsProgramItem.item_type == 'arcade_game'`).

Deliberately separate from:
- `app/models/games/game.py` (`games`), which is the facilitator-led Live Quiz
  (Kahoot-style) domain.
- `app/models/missions/mission.py` (`missions`), which carries team-formation,
  multi-variant, and Madar 9-step design wizard machinery.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class ArcadeGame(Base):
    """One of the 51 SatKit mini-games/simulations. `game_key` matches `g.id`
    inside `SpacePoint Mission Arcade.html` (e.g. 'brain', 'eclipse', 'orbit3d')."""

    __tablename__ = "arcade_games"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_key = Column(String(32), nullable=False, unique=True, index=True)
    position = Column(Integer, nullable=False, default=1)
    module_key = Column(String(16), nullable=False, index=True)  # intro|cdhs|sw|eps|adcs|comms|mech|env|ops
    module_no = Column(String(8), nullable=False)                # '1', '2', '2.1', '3', ...
    module_name = Column(String(64), nullable=False)
    kind = Column(String(16), nullable=False, default="Checkpoint")  # Checkpoint|Mission
    is_3d = Column(Boolean, nullable=False, default=False, server_default="false")
    title = Column(String(128), nullable=False)
    blurb = Column(Text, nullable=True)
    lesson_explorer = Column(String(255), nullable=True)
    lesson_engineer = Column(String(255), nullable=True)
    time_explorer_seconds = Column(Integer, nullable=False, default=45)
    time_engineer_seconds = Column(Integer, nullable=False, default=60)
    points_explorer = Column(Integer, nullable=False, default=50, server_default="50")
    points_engineer = Column(Integer, nullable=False, default=75, server_default="75")
    # Retire, never delete (Rule F1)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ArcadeGameAttempt(Base):
    """One completed play-through of an ArcadeGame by a user.

    `program_item_id` is optional (nullable):
    - NULL when played standalone from `/learn/arcade`.
    - Set when launched from a specific `LmsProgramItem` tile on `RoadmapBoard`.

    Autopass reconciliation (`services/lms/program.py::_arcade_game_item_done`)
    queries by `(user_id, game_id, mode, passed=True)` regardless of whether
    `program_item_id` is set, so passing a game in standalone play automatically
    satisfies any program checklist step requiring that game and mode.
    """

    __tablename__ = "arcade_game_attempts"
    __table_args__ = (
        Index("ix_arcade_game_attempts_user_game_mode", "user_id", "game_id", "mode"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    game_id = Column(UUID(as_uuid=True), ForeignKey("arcade_games.id", ondelete="RESTRICT"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    program_item_id = Column(
        UUID(as_uuid=True), ForeignKey("lms_program_items.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    cohort_id = Column(UUID(as_uuid=True), ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True)
    # 'explorer' | 'engineer'
    mode = Column(String(16), nullable=False)
    score = Column(Integer, nullable=False)            # 0..100
    accuracy = Column(Integer, nullable=False)         # 0..100 percentage
    passed = Column(Boolean, nullable=False, default=False)
    elapsed_seconds = Column(Integer, nullable=False, default=0)
    attempt_no = Column(Integer, nullable=False, default=1)
    # [{"ok": bool, "t": str}, ...] debrief notes emitted by the game's evaluate()
    notes = Column(JSONB, nullable=False, default=list, server_default="[]")
    completed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
