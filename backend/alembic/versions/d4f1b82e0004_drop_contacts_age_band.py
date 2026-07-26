"""drop contacts.age_band (V2 amendment: age tracked via date_of_birth only, no bracket)

Revision ID: d4f1b82e0004
Revises: c3e0a71d0003
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d4f1b82e0004"
down_revision = "c3e0a71d0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("contacts", "age_band")


def downgrade() -> None:
    op.add_column("contacts", sa.Column("age_band", sa.String(length=16), nullable=True))
