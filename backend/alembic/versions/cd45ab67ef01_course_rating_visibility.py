"""Add show_rating and rating_auto_hidden to courses

Revision ID: cd45ab67ef01
Revises: cc34ef56ab99
Create Date: 2026-11-01 17:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "cd45ab67ef01"
down_revision = "cc34ef56ab99"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column("show_rating", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "courses",
        sa.Column("rating_auto_hidden", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("courses", "rating_auto_hidden")
    op.drop_column("courses", "show_rating")
