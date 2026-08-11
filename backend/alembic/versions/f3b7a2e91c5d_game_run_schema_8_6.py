"""game run/participant/answer schema + scoring (Live Games Phase 2C, 8-6, 2026-08-12)

`game_runs` (one row per instructor "Start", run_no increments per
assignment on restart — D15), `game_participants` (nickname snapshotted
at join, D2), `game_answers` (one row per participant+question,
question_id SET NULL so a mid-game question delete, D13/D16, is never
blocked by its own answer history). See models/games/run.py for the
full design note.

Revision ID: f3b7a2e91c5d
Revises: c1c8a3f9d4e2
Create Date: 2026-08-12 11:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3b7a2e91c5d'
down_revision: Union[str, None] = 'c1c8a3f9d4e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "game_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("assignment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_session_assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="lobby"),
        sa.Column("current_question_position", sa.Integer(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("assignment_id", "run_no", name="uq_game_runs_assignment_run_no"),
        sa.CheckConstraint("status IN ('lobby', 'live', 'ended')", name="ck_game_runs_status"),
    )
    op.create_index("ix_game_runs_assignment_id", "game_runs", ["assignment_id"])

    op.create_table(
        "game_participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("nickname_snapshot", sa.String(64), nullable=False),
        sa.Column("avatar", sa.String(64), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "user_id", name="uq_game_participants_run_user"),
    )
    op.create_index("ix_game_participants_run_id", "game_participants", ["run_id"])

    op.create_table(
        "game_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("participant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_participants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("game_session_questions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("selected_option_index", sa.Integer(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("elapsed_seconds", sa.Numeric(6, 2), nullable=True),
        sa.Column("points_awarded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("participant_id", "question_id", name="uq_game_answers_participant_question"),
    )
    op.create_index("ix_game_answers_participant_id", "game_answers", ["participant_id"])


def downgrade() -> None:
    op.drop_index("ix_game_answers_participant_id", table_name="game_answers")
    op.drop_table("game_answers")
    op.drop_index("ix_game_participants_run_id", table_name="game_participants")
    op.drop_table("game_participants")
    op.drop_index("ix_game_runs_assignment_id", table_name="game_runs")
    op.drop_table("game_runs")
