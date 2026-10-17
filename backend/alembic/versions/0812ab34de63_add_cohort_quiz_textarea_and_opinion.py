"""Add text_answer and nullable is_correct to cohort_quiz_answers (2026-10)

Revision ID: 0812ab34de63
Revises: 0712ab34de62
Create Date: 2026-10-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0812ab34de63"
down_revision = "0712ab34de62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cohort_quiz_answers", sa.Column("text_answer", sa.Text(), nullable=True))
    op.alter_column("cohort_quiz_answers", "is_correct", existing_type=sa.Boolean(), nullable=True)


def downgrade() -> None:
    op.drop_column("cohort_quiz_answers", "text_answer")
    op.alter_column("cohort_quiz_answers", "is_correct", existing_type=sa.Boolean(), nullable=False, server_default="false")
