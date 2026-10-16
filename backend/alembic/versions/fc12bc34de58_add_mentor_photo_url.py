"""add photo_url to mentor_profiles

Revision ID: fc12bc34de58
Revises: fb12bc34de57
Create Date: 2026-10-16
"""

from alembic import op
import sqlalchemy as sa


revision = "fc12bc34de58"
down_revision = "fb12bc34de57"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mentor_profiles", sa.Column("photo_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("mentor_profiles", "photo_url")
