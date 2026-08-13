"""drop design_step_gates (Design v2, 7D-0)

Instructor-paced release of budget steps is removed. The operator's call
(Design v2 D1) is that instructors stay out of the mission entirely — the
same decision already made for the operate mission — and difficulty lives
in `mission_variants` instead.

Worth recording why this is a delete rather than a deprecation: the feature
was already inert. `gating.py::is_step_unlocked` had been hardcoded to
default-unlocked since 2026-08-12 because no frontend screen to unlock a
step was ever built, so no cohort has a row here and nothing has ever been
gated in production.

`designs.cohort_id` is deliberately kept. It was the gating scope, but it
is still useful attribution — it is what lets the admin progress grid
report designs by cohort.

Revision ID: d4a1c07e5b32
Revises: c15604b9448b
"""

import sqlalchemy as sa
from alembic import op

revision = "d4a1c07e5b32"
down_revision = "c15604b9448b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("design_step_gates")


def downgrade() -> None:
    op.create_table(
        "design_step_gates",
        sa.Column("cohort_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_key", sa.String(length=20), nullable=False),
        sa.Column("is_unlocked", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["cohort_id"], ["cohorts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cohort_id", "step_key", name="pk_design_step_gates"),
    )
