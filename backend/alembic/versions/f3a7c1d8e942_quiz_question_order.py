"""item_progress: quiz_question_order (random-N quizzes, 2026-09-01)

Adds a nullable JSONB list[int] column recording which question indices
(and in what order) were sampled for a student's current, not-yet-graded
attempt of a quiz configured with `random_count`. Cleared back to NULL by
submit_quiz after grading, so the next view draws a fresh random sample —
see services/lms/quiz.py::get_quiz_display_order for the full lifecycle.

Revision ID: f3a7c1d8e942
Revises: c8e1f9a4d2b6
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f3a7c1d8e942"
down_revision = "c8e1f9a4d2b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item_progress", sa.Column("quiz_question_order", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("item_progress", "quiz_question_order")
