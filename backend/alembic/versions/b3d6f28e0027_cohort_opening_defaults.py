"""Cohort-level opening defaults + bulk session actions support

Operator ask (2026-08-01): "do stuff at cohort level, then if you want to
customize, override in session view" — for openings/roles, same as materials
already does for program -> cohort -> session. `cohort_openings` is the
template; a session with its own `session_openings` rows overrides it, one
that has none inherits it (resolved in `openings_for_session`, not stored
twice).

No columns needed for the bulk-assign / bulk-open-call endpoints landing in
the same batch — both just loop the existing per-session service calls.

Revision ID: b3d6f28e0027
Revises: a2c5e17d0026
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "b3d6f28e0027"
down_revision = "a2c5e17d0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cohort_openings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True), sa.ForeignKey("delivery_roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("slots", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("amount_aed", sa.Numeric(10, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("cohort_id", "role_id", name="uq_cohort_opening_role"),
    )
    op.create_index("ix_cohort_openings_cohort_id", "cohort_openings", ["cohort_id"])


def downgrade() -> None:
    op.drop_index("ix_cohort_openings_cohort_id", table_name="cohort_openings")
    op.drop_table("cohort_openings")
