"""duration_hours on programs, cohorts and sessions (I5-2)

Operator decision: duration is set on the **program**, overridable on the
**cohort**, overridable again on the **session**.

This is the same shape `price` already uses (`Session.price` falls back to
`Program.price`), so it follows existing precedent rather than introducing a
new idea — it just adds the middle rung the price chain never had.

Why it matters beyond tidiness: `payment_sessions.duration_hours` is a column
the generated letter prints and, until now, had **no source anywhere** —
sessions carried `meeting_date` and `starts_at` and nothing about how long
they ran. That is why the CEO was typing hours into Word. The payment line
now prefills from whatever this chain resolves to.

Numeric(5, 2) — a workshop is 2.5 or 3 hours, never 1000.

Revision ID: c1b5d27f0021
Revises: b1f6a38d0020
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op

revision = "c1b5d27f0021"
down_revision = "b1f6a38d0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("programs", "cohorts", "sessions"):
        op.add_column(table, sa.Column("duration_hours", sa.Numeric(5, 2), nullable=True))


def downgrade() -> None:
    for table in ("programs", "cohorts", "sessions"):
        op.drop_column(table, "duration_hours")
