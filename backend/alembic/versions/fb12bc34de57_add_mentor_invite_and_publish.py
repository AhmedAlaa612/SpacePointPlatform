"""add invite_code and is_published to mentor_profiles

Revision ID: fb12bc34de57
Revises: fa12bc34de56
Create Date: 2026-10-16
"""

from alembic import op
import sqlalchemy as sa


revision = "fb12bc34de57"
down_revision = "fa12bc34de56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mentor_profiles", sa.Column("invite_code", sa.String(50), nullable=True))
    op.add_column("mentor_profiles", sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("mentor_profiles", "is_published")
    op.drop_column("mentor_profiles", "invite_code")
