"""Add image_url to assessment_questions

Revision ID: 9017f37d67ed
Revises: de56bc78fa02
Create Date: 2026-11-02 01:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "9017f37d67ed"
down_revision = "de56bc78fa02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assessment_questions", sa.Column("image_url", sa.String(length=512), nullable=True))

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = inspector.get_table_names()

    if "pre_session_quiz_questions" in table_names:
        op.execute("""
            UPDATE assessment_questions aq
            SET image_url = psq.image_url
            FROM pre_session_quiz_questions psq
            WHERE aq.id = psq.id AND psq.image_url IS NOT NULL
        """)


def downgrade() -> None:
    op.drop_column("assessment_questions", "image_url")
