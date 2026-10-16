"""add linkedin_url to mentor_profiles

Revision ID: ff12bc34de61
Revises: fe12bc34de60
Create Date: 2026-10-16
"""

from alembic import op
import sqlalchemy as sa


revision = "ff12bc34de61"
down_revision = "fe12bc34de60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mentor_profiles", sa.Column("linkedin_url", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("mentor_profiles", "linkedin_url")
