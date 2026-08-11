"""game session assignment + snapshot copy (Live Games Phase 2C, 8-4, 2026-08-12)

`game_session_assignments` (a Game template attached to one Session, with
an instructor-facing note and its own copy of the template's default
config, D11) and `game_session_questions` (the assignment's own snapshot
of the question set, D12 — no FK back to `game_questions`, editing this
copy never touches the shared template). See models/games/session_assignment.py
for the full design note.

Revision ID: c1c8a3f9d4e2
Revises: a94e22265a38
Create Date: 2026-08-12 09:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c1c8a3f9d4e2'
down_revision: Union[str, None] = 'a94e22265a38'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "game_session_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("game_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("games.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("instructor_note", sa.Text(), nullable=True),
        sa.Column("time_limit_seconds", sa.Integer(), nullable=False),
        sa.Column("floor_pct", sa.Integer(), nullable=False),
        sa.Column("blackout_count", sa.Integer(), nullable=False),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_game_session_assignments_session_id", "game_session_assignments", ["session_id"])

    op.create_table(
        "game_session_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_session_assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("time_limit_seconds", sa.Integer(), nullable=True),
        sa.Column("points_mode", sa.String(8), nullable=False, server_default="normal"),
        sa.UniqueConstraint("assignment_id", "position", name="uq_game_session_questions_assignment_position"),
        sa.CheckConstraint("points_mode IN ('normal', 'double')", name="ck_game_session_questions_points_mode"),
    )
    op.create_index("ix_game_session_questions_assignment_id", "game_session_questions", ["assignment_id"])


def downgrade() -> None:
    op.drop_index("ix_game_session_questions_assignment_id", table_name="game_session_questions")
    op.drop_table("game_session_questions")
    op.drop_index("ix_game_session_assignments_session_id", table_name="game_session_assignments")
    op.drop_table("game_session_assignments")
