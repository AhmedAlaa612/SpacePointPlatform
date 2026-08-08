"""Add `users.city_other` (2026-08-08, chained after the applications→city
column).

The city pickers everywhere gained an "Other (type it)" option for countries
with no SpacePoint city — the typed value lands here (see
models/user.py::User.city_other). Nullable: most rows pick a real city or
none at all. Downgrade just drops the column (values are opt-in free text,
nothing else reads it).
"""

import sqlalchemy as sa
from alembic import op

revision = "f0a1b2c3d4e5"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("city_other", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "city_other")