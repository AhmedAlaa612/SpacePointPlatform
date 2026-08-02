"""Cohort-level kit defaults

Operator ask, Phase 3 follow-up to the session kit-loop (I2-1/I2-2): ops
manages one kit list per cohort instead of re-picking the same kits on every
session it runs. A session inherits its cohort's default kit set until that
session's own kit activity happens — ops assigns/removes a kit directly on
it, or an instructor receives/returns one — at which point the cohort's
current default is copied ("materialized") into real `session_kits` rows for
that one session, and the session is independent of the cohort default from
then on, including if the cohort default later changes.

`cohort_kits` deliberately has none of `session_kits`' received/returned/
ops-confirmed columns. Nothing is received or returned at the cohort level —
only a session that actually happens, on a real date, with a kit someone can
physically hold. A kit is also a serialised, single-instance resource (see
`Kit`'s own docstring): the same physical box cannot be "in" two sessions'
default lists in any sense beyond a label. So this table is a *default
label* — which kits this cohort's sessions should start with — not a
reservation of anything. Nothing here contends with `session_kits` for the
same box; only materialization ever creates a claim on one.

`sessions.kits_overridden` is the flag that makes materialization sticky and
one-directional. Row count alone cannot carry this signal: a session ops
deliberately clears down to zero kits is legitimately zero rows, and without
the flag that is indistinguishable from a session that has simply never been
touched and should keep inheriting. The flag, once true, stays true — the
service layer (not this migration) is what actually enforces "materialize
once, then never revert."

Revision ID: a3c7f95e0037
Revises: b88f272265ef
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "a3c7f95e0037"
down_revision = "b88f272265ef"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cohort_kits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kit_id", UUID(as_uuid=True), sa.ForeignKey("kits.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("cohort_id", "kit_id", name="uq_cohort_kit"),
    )
    op.create_index("ix_cohort_kits_cohort_id", "cohort_kits", ["cohort_id"])
    op.create_index("ix_cohort_kits_kit_id", "cohort_kits", ["kit_id"])

    op.add_column(
        "sessions",
        sa.Column("kits_overridden", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("sessions", "kits_overridden")

    op.drop_index("ix_cohort_kits_kit_id", table_name="cohort_kits")
    op.drop_index("ix_cohort_kits_cohort_id", table_name="cohort_kits")
    op.drop_table("cohort_kits")
