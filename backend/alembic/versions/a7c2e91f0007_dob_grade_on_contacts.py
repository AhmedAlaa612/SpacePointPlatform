"""contacts.date_of_birth + contacts.grade (CEO request, 2026-07-24 — re-adds DOB, purely informational, no enforcement; adds grade, new)

Revision ID: a7c2e91f0007
Revises: f6b3d84a0006
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7c2e91f0007"
down_revision = "f6b3d84a0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("contacts", sa.Column("grade", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("contacts", "grade")
    op.drop_column("contacts", "date_of_birth")
