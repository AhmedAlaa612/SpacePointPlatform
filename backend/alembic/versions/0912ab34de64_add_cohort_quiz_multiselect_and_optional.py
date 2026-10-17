"""Add is_optional to cohort_quiz_questions and selected_option_indices to cohort_quiz_answers (2026-10)

Revision ID: 0912ab34de64
Revises: 0812ab34de63
Create Date: 2026-10-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0912ab34de64"
down_revision = "0812ab34de63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cohort_quiz_questions", sa.Column("is_optional", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("cohort_quiz_answers", sa.Column("selected_option_indices", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("cohort_quiz_answers", "selected_option_indices")
    op.drop_column("cohort_quiz_questions", "is_optional")
