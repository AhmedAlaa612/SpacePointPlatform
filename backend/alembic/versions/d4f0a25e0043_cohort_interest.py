"""cohort_interest — "notify me" capture for planned public cohorts (2026-08-07)

Backs the planned→registration_open dual-CTA the operator asked for: a
`planned` public cohort shows "Notify me" instead of "Register now", and a
`cohort_interest` row is created via the same `resolve_or_create_contact`
identity flow as real registration — deliberately not a `Registration` row,
since no payment/attendance/ticket state applies to "just interested."
`send_cohort_interest_notifications` (new ARQ job) emails everyone here for a
cohort once ops flips its status to `registration_open`.

Revision ID: d4f0a25e0043
Revises: c3e9f14d0042
Create Date: 2026-08-07
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d4f0a25e0043"
down_revision = "c3e9f14d0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cohort_interest",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "contact_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "cohort_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("contact_id", "cohort_id", name="uq_cohort_interest_contact_cohort"),
    )
    op.create_index("ix_cohort_interest_cohort_id", "cohort_interest", ["cohort_id"])


def downgrade() -> None:
    op.drop_index("ix_cohort_interest_cohort_id", table_name="cohort_interest")
    op.drop_table("cohort_interest")
