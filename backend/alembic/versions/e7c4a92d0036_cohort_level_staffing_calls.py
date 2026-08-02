"""Cohort-level staffing calls

Operator ask (2026-08-01, W4 follow-up): ops wants to open one call across a
*chosen subset* of a cohort's sessions — not necessarily all of them — and
later close it for a chosen subset too, while seeing/managing the whole
thing as one cohesive campaign instead of N independent per-session calls
they have to click through one at a time.

`open_call_for_cohort` (migration-less, service-only, predates this) already
bulk-applies `SessionCall` rows across every unstaffed session in a cohort,
but it's a fire-and-forget loop with no grouping: once opened, there is no
record that those N calls were "the same ask", so closing or viewing them as
a set isn't possible. `cohort_calls` is that missing grouping row; it does
NOT replace or change per-session staffing in any way — `Session.
staffing_status` and `SessionCall` keep meaning exactly what they meant
before (see staffing.py's and session_call.py's docstrings). A session can
still run its own fully independent call, untouched by any cohort call
running alongside it on the same session.

`cohort_calls.status` is a derived summary, the same pattern as `Session.
staffing_status`: "open" while at least one linked `SessionCall` (via the
new `session_calls.cohort_call_id`) is still open, "closed" once none are —
synced by the service layer on every mutation, never set independently.

`cohort_call_targets` mirrors `session_call_targets`'s "absent means
unrestricted" contract at the cohort-call level: a cohort call with no
target rows is a public call across every session it touches.

`session_calls.cohort_call_id` is nullable and SET NULL on delete — a
`SessionCall` opened directly via the existing single-session `open_call`
path never gets one, and dropping a `CohortCall` (not that anything in this
codebase actually deletes one) leaves its `SessionCall` rows intact, just
ungrouped.

Revision ID: e7c4a92d0036
Revises: d8a2c94e0035
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "e7c4a92d0036"
down_revision = "d8a2c94e0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cohort_calls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("label", sa.String(64), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cohort_calls_cohort_id", "cohort_calls", ["cohort_id"])

    op.create_table(
        "cohort_call_targets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_call_id", UUID(as_uuid=True), sa.ForeignKey("cohort_calls.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("cohort_call_id", "user_id", name="uq_cohort_call_target"),
    )
    op.create_index("ix_cohort_call_targets_cohort_call_id", "cohort_call_targets", ["cohort_call_id"])

    op.add_column(
        "session_calls",
        sa.Column("cohort_call_id", UUID(as_uuid=True), sa.ForeignKey("cohort_calls.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_session_calls_cohort_call_id", "session_calls", ["cohort_call_id"])


def downgrade() -> None:
    op.drop_index("ix_session_calls_cohort_call_id", table_name="session_calls")
    op.drop_column("session_calls", "cohort_call_id")

    op.drop_index("ix_cohort_call_targets_cohort_call_id", table_name="cohort_call_targets")
    op.drop_table("cohort_call_targets")

    op.drop_index("ix_cohort_calls_cohort_id", table_name="cohort_calls")
    op.drop_table("cohort_calls")
