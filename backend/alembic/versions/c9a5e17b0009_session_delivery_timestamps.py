"""W5 S5-1: instructor delivery — Session gains started_at/completed_at so
start_session/mark_done have something to write. Both nullable, no default:
a never-started session is simply NULL, not a sentinel date.

Revision ID: c9a5e17b0009
Revises: b8d4f02a0008
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c9a5e17b0009"
down_revision = "b8d4f02a0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sessions", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "completed_at")
    op.drop_column("sessions", "started_at")
