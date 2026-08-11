"""game template schema (Live Games Phase 2C, 8-3, 2026-08-12)

`games` (the reusable template, D4) and `game_questions` (points_mode
normal|double, D8 — not a free-typed number). See
models/games/game.py for the full design note.

Revision ID: a94e22265a38
Revises: 851d4a6219af
Create Date: 2026-08-11 22:15:04.886956

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a94e22265a38'
down_revision: Union[str, None] = '851d4a6219af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("default_time_limit_seconds", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("default_floor_pct", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("default_blackout_count", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "game_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("time_limit_seconds", sa.Integer(), nullable=True),
        sa.Column("points_mode", sa.String(8), nullable=False, server_default="normal"),
        sa.UniqueConstraint("game_id", "position", name="uq_game_questions_game_position"),
        sa.CheckConstraint("points_mode IN ('normal', 'double')", name="ck_game_questions_points_mode"),
    )
    op.create_index("ix_game_questions_game_id", "game_questions", ["game_id"])


def downgrade() -> None:
    op.drop_index("ix_game_questions_game_id", table_name="game_questions")
    op.drop_table("game_questions")
    op.drop_table("games")
