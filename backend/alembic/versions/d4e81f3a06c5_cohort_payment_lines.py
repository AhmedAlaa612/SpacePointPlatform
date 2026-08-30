"""Cohort-aggregated payment lines

Operator ask, 2026-08-24 (WhatsApp): a payment letter should carry one row per
cohort — the cohort's date range, the role, and "n sessions x rate = total" —
rather than one row per session. The driver is not cosmetic: the bank charges
extra once a month's transactions exceed ten, so several cohorts are settled
on a single letter for one instructor, and an itemised day list makes that
letter unreadable.

`payment_sessions` gains three nullable columns: `cohort_id`, `session_count`
and `rate_aed`. Every existing row stays valid and a manual or single-session
line leaves them NULL and prints exactly as it always has.

`payment_session_coverage` is the anti-double-billing key generalised from one
to N. The rule in `services/sessions/journey.py` has always been "a session is
billed iff a `payment_sessions.session_id` under this instructor's own letters
points at it", and one column can only point at one session. `unbilled_sessions`
now also consults this table. Existing rows keep their `session_id` and need no
data migration — nothing is backfilled here, because every historical line
genuinely does cover exactly the one session it names.

Note the deliberate FK asymmetry: `payment_sessions.session_id` is SET NULL so
a deleted session cannot erase a payment record, while coverage rows CASCADE —
the line must survive, its bookkeeping need not.

Revision ID: d4e81f3a06c5
Revises: c7b34e18d902
Create Date: 2026-08-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "d4e81f3a06c5"
down_revision = "c7b34e18d902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_sessions",
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True),
    )
    op.add_column("payment_sessions", sa.Column("session_count", sa.Integer(), nullable=True))
    op.add_column("payment_sessions", sa.Column("rate_aed", sa.Float(), nullable=True))

    op.create_table(
        "payment_session_coverage",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "payment_session_id", UUID(as_uuid=True),
            sa.ForeignKey("payment_sessions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "session_id", UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.UniqueConstraint("payment_session_id", "session_id", name="uq_payment_session_coverage"),
    )
    op.create_index(
        "ix_payment_session_coverage_payment_session_id", "payment_session_coverage", ["payment_session_id"]
    )
    op.create_index("ix_payment_session_coverage_session_id", "payment_session_coverage", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_session_coverage_session_id", table_name="payment_session_coverage")
    op.drop_index("ix_payment_session_coverage_payment_session_id", table_name="payment_session_coverage")
    op.drop_table("payment_session_coverage")

    op.drop_column("payment_sessions", "rate_aed")
    op.drop_column("payment_sessions", "session_count")
    op.drop_column("payment_sessions", "cohort_id")
