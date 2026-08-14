"""Restart a live game in place instead of creating a new run.

D15 originally made Restart create a brand-new `GameRun`. In use that
turned "run that again" into a room evacuation: the join code changed and
every student was thrown back to the code screen. A restart is a do-over of
the same game with the same people, so it now resets the same row.

Two schema changes make that safe:

* `game_runs.restart_no` — the points ledger keys awards by run and
  question. Replaying a question in the same run would collide with the key
  from the attempt that was just reversed and silently award nothing, so the
  restart count joins the key.
* `game_answers` unique constraint becomes **partial**. A participant may
  answer a question once *that still counts*; the reversed rows from before
  a restart stay as history rather than being deleted, and the replay writes
  a fresh row alongside them.

Revision ID: b3f1c9d47a10
Revises: a91e4d7c2b08
"""

import sqlalchemy as sa
from alembic import op

revision = "b3f1c9d47a10"
down_revision = "a91e4d7c2b08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "game_runs",
        sa.Column("restart_no", sa.Integer(), nullable=False, server_default="0"),
    )
    op.drop_constraint(
        "uq_game_answers_participant_question", "game_answers", type_="unique",
    )
    op.create_index(
        "uq_game_answers_participant_question",
        "game_answers",
        ["participant_id", "question_id"],
        unique=True,
        postgresql_where=sa.text("reversed_at IS NULL"),
    )


def downgrade() -> None:
    # Reversed duplicates have to go before an absolute constraint can hold
    # again — they are exactly the rows the partial index was added to allow.
    op.execute(
        """
        DELETE FROM game_answers a
        USING game_answers b
        WHERE a.participant_id = b.participant_id
          AND a.question_id = b.question_id
          AND a.reversed_at IS NOT NULL
          AND a.id <> b.id
        """
    )
    op.drop_index("uq_game_answers_participant_question", table_name="game_answers")
    op.create_unique_constraint(
        "uq_game_answers_participant_question", "game_answers",
        ["participant_id", "question_id"],
    )
    op.drop_column("game_runs", "restart_no")
