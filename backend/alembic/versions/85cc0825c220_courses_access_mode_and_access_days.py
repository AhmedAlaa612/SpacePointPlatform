"""courses.access_mode + courses.access_days (P1-2, LMS Phase 2 Stage 1, 2026-08-10).

`access_mode`: open|invite|paid — existing courses default to 'open', which
is exactly today's self-enrol-if-logged-in behaviour, so this is a no-op
for every existing row.

`access_days` pulled forward from Stage S into this stage per the audit
(LMS_DESIGN_AUDIT.md §9.3(d)): it was scheduled in PS-2 while the
`enrollments.expires_at` column it feeds lands here in P1-3. Shipping them
in the same stage means there's never a window where per-course expiry looks
implemented and silently isn't.
"""

import sqlalchemy as sa
from alembic import op

revision = "85cc0825c220"
down_revision = "efeef0a62c62"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "courses",
        sa.Column("access_mode", sa.String(12), nullable=False, server_default="open"),
    )
    op.add_column("courses", sa.Column("access_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("courses", "access_days")
    op.drop_column("courses", "access_mode")
