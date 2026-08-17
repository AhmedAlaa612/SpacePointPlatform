"""Freeze the date printed on an instructor's contract.

`_ensure_contract` re-renders the unsigned contract with `date.today()` on
every profile load (by design, for name/city — see its docstring), which
means the date shown drifts forward every day until signing instead of
reflecting when the person actually became an instructor. There was no
column to freeze it against. `instructor_since` is that column: set once,
at whichever event actually granted the instructor role (applicant
approval, an admin editing roles directly, or a bulk import), and never
touched again. Backfilled from `instructor_profiles.created_at` for
existing rows — the profile is created at approval time today, so its
`created_at` is the closest existing proxy for the real historical date.

Revision ID: f4c8b1e6a923
Revises: e3a9c6f2b871
"""

import sqlalchemy as sa
from alembic import op

revision = "f4c8b1e6a923"
down_revision = "e3a9c6f2b871"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("instructor_profiles", sa.Column("instructor_since", sa.Date(), nullable=True))
    op.execute(
        "UPDATE instructor_profiles SET instructor_since = created_at::date "
        "WHERE instructor_since IS NULL"
    )


def downgrade() -> None:
    op.drop_column("instructor_profiles", "instructor_since")
