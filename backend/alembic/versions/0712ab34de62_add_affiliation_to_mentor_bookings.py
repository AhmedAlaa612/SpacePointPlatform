"""add affiliation to mentor_bookings

Revision ID: 0712ab34de62
Revises: f7a8b9c0d1e2
Create Date: 2026-10-17
"""

from alembic import op
import sqlalchemy as sa


revision = "0712ab34de62"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mentor_bookings", sa.Column("affiliation", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("mentor_bookings", "affiliation")
