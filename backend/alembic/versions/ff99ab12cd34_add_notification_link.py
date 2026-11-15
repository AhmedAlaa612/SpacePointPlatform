"""Add link column to notifications for 1-click deep-linking

Revision ID: ff99ab12cd34
Revises: fc16d08f0055
Create Date: 2026-11-15 01:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "ff99ab12cd34"
down_revision = "fc16d08f0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("link", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "link")
