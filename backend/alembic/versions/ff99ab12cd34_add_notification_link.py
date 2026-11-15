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
    op.execute(sa.text("ALTER TABLE notifications ADD COLUMN IF NOT EXISTS link VARCHAR(500)"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE notifications DROP COLUMN IF EXISTS link"))
