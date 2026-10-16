"""add contact_email and show_contact_button to mentor_profiles

Revision ID: fe12bc34de60
Revises: fd12bc34de59
Create Date: 2026-10-16
"""

from alembic import op
import sqlalchemy as sa


revision = "fe12bc34de60"
down_revision = "fd12bc34de59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mentor_profiles", sa.Column("contact_email", sa.String(255), nullable=True))
    op.add_column("mentor_profiles", sa.Column("show_contact_button", sa.Boolean(), nullable=False, server_default=sa.text("true")))


def downgrade() -> None:
    op.drop_column("mentor_profiles", "show_contact_button")
    op.drop_column("mentor_profiles", "contact_email")
