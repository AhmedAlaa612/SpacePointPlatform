"""Add cohort_payment_decisions table and payment_letters.paid_at timestamp.

Revision ID: d8e9f0a1b2c3
Revises: b0c1d2e3f4a5
Create Date: 2026-11-28 13:05:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "b0c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "payment_letters" in tables:
        cols = {c["name"] for c in insp.get_columns("payment_letters")}
        if "paid_at" not in cols:
            op.add_column(
                "payment_letters",
                sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            )

    if "cohort_payment_decisions" not in tables:
        op.create_table(
            "cohort_payment_decisions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "cohort_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("cohorts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "instructor_user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("decision", sa.String(length=16), nullable=False),
            sa.Column(
                "payment_letter_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("payment_letters.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "payment_session_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("payment_sessions.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("role_name", sa.String(length=64), nullable=True),
            sa.Column("sessions_count", sa.Integer(), nullable=True),
            sa.Column("hours", sa.Float(), nullable=True),
            sa.Column("rate_aed", sa.Float(), nullable=True),
            sa.Column("total_aed", sa.Float(), nullable=True),
            sa.Column(
                "decided_by_admin_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "decided_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("NOW()"),
            ),
            sa.UniqueConstraint("cohort_id", "instructor_user_id", name="uq_cohort_payment_decision"),
        )
        op.create_index(
            "ix_cohort_payment_decisions_cohort_id",
            "cohort_payment_decisions",
            ["cohort_id"],
        )
        op.create_index(
            "ix_cohort_payment_decisions_instructor_user_id",
            "cohort_payment_decisions",
            ["instructor_user_id"],
        )
        op.create_index(
            "ix_cohort_payment_decisions_payment_letter_id",
            "cohort_payment_decisions",
            ["payment_letter_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    if "cohort_payment_decisions" in tables:
        op.drop_index("ix_cohort_payment_decisions_payment_letter_id", table_name="cohort_payment_decisions")
        op.drop_index("ix_cohort_payment_decisions_instructor_user_id", table_name="cohort_payment_decisions")
        op.drop_index("ix_cohort_payment_decisions_cohort_id", table_name="cohort_payment_decisions")
        op.drop_table("cohort_payment_decisions")

    if "payment_letters" in tables:
        cols = {c["name"] for c in insp.get_columns("payment_letters")}
        if "paid_at" in cols:
            op.drop_column("payment_letters", "paid_at")
