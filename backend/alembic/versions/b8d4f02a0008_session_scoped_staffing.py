"""W4 staffing marketplace: staffing_status moves from cohorts to sessions;
instructor_interests becomes session-scoped instead of cohort-scoped
(operator decision 2026-07-24 — assignment is already per-session, and the
CEO's own description was "a session is made available", not a cohort).

Both tables are empty in every environment this has run in (staffing/
interest were never wired to anything before W4) — a clean drop-and-add,
no data to migrate.

Revision ID: b8d4f02a0008
Revises: a7c2e91f0007
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b8d4f02a0008"
down_revision = "a7c2e91f0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("staffing_status", sa.String(length=16), nullable=False, server_default="unstaffed"),
    )
    op.alter_column("sessions", "staffing_status", server_default=None)
    op.drop_column("cohorts", "staffing_status")

    op.drop_constraint("uq_instructor_interest", "instructor_interests", type_="unique")
    op.drop_column("instructor_interests", "cohort_id")
    op.add_column(
        "instructor_interests",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_unique_constraint("uq_instructor_interest", "instructor_interests", ["session_id", "user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_instructor_interest", "instructor_interests", type_="unique")
    op.drop_column("instructor_interests", "session_id")
    op.add_column(
        "instructor_interests",
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_unique_constraint("uq_instructor_interest", "instructor_interests", ["cohort_id", "user_id"])

    op.add_column(
        "cohorts",
        sa.Column("staffing_status", sa.String(length=16), nullable=False, server_default="unstaffed"),
    )
    op.alter_column("cohorts", "staffing_status", server_default=None)
    op.drop_column("sessions", "staffing_status")
