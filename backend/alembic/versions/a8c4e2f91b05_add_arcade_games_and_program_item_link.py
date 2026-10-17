"""Add arcade_games, arcade_game_attempts, and lms_program_items arcade columns.

Revision ID: a8c4e2f91b05
Revises: 0912ab34de64
Create Date: 2026-10-17 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a8c4e2f91b05"
down_revision: Union[str, None] = "0912ab34de64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "arcade_games",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("game_key", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("module_key", sa.String(length=16), nullable=False),
        sa.Column("module_no", sa.String(length=8), nullable=False),
        sa.Column("module_name", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="Checkpoint"),
        sa.Column("is_3d", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("blurb", sa.Text(), nullable=True),
        sa.Column("lesson_explorer", sa.String(length=255), nullable=True),
        sa.Column("lesson_engineer", sa.String(length=255), nullable=True),
        sa.Column("time_explorer_seconds", sa.Integer(), nullable=False, server_default="45"),
        sa.Column("time_engineer_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("points_explorer", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("points_engineer", sa.Integer(), nullable=False, server_default="75"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("game_key", name="uq_arcade_games_game_key"),
    )
    op.create_index("ix_arcade_games_game_key", "arcade_games", ["game_key"], unique=True)
    op.create_index("ix_arcade_games_module_key", "arcade_games", ["module_key"], unique=False)

    op.create_table(
        "arcade_game_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("arcade_games.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("program_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_program_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Integer(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("elapsed_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_arcade_game_attempts_game_id", "arcade_game_attempts", ["game_id"])
    op.create_index("ix_arcade_game_attempts_user_id", "arcade_game_attempts", ["user_id"])
    op.create_index("ix_arcade_game_attempts_program_item_id", "arcade_game_attempts", ["program_item_id"])
    op.create_index("ix_arcade_game_attempts_user_game_mode", "arcade_game_attempts", ["user_id", "game_id", "mode"])

    op.add_column(
        "lms_program_items",
        sa.Column("arcade_game_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("arcade_games.id", ondelete="RESTRICT"), nullable=True),
    )
    op.add_column(
        "lms_program_items",
        sa.Column("arcade_game_mode", sa.String(length=16), nullable=True, server_default="explorer"),
    )


def downgrade() -> None:
    op.drop_column("lms_program_items", "arcade_game_mode")
    op.drop_column("lms_program_items", "arcade_game_id")
    op.drop_index("ix_arcade_game_attempts_user_game_mode", table_name="arcade_game_attempts")
    op.drop_index("ix_arcade_game_attempts_program_item_id", table_name="arcade_game_attempts")
    op.drop_index("ix_arcade_game_attempts_user_id", table_name="arcade_game_attempts")
    op.drop_index("ix_arcade_game_attempts_game_id", table_name="arcade_game_attempts")
    op.drop_table("arcade_game_attempts")
    op.drop_index("ix_arcade_games_module_key", table_name="arcade_games")
    op.drop_index("ix_arcade_games_game_key", table_name="arcade_games")
    op.drop_table("arcade_games")
