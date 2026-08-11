"""design_step_gates (P7-7, LMS Phase 2 Stage 7, 2026-08-11).

Server-side step gating per cohort, replacing Madar's page_access (which
was enforced only in the browser — S1). A missing row means locked.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "94eaeb5ddbde"
down_revision = "b6de791de443"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "design_step_gates",
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_key", sa.String(20), nullable=False),
        sa.Column("is_unlocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("cohort_id", "step_key", name="pk_design_step_gates"),
    )


def downgrade() -> None:
    op.drop_table("design_step_gates")
