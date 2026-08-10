"""cohort_curriculum (P4-1, LMS Phase 2 Stage 4, 2026-08-10).

Same shape as program_curriculum, one level down — a cohort with any rows
here overrides its program's curriculum outright (never merged), the same
idiom session_materials already uses.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "2be404a89eae"
down_revision = "596e821dc2df"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cohort_curriculum",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.UniqueConstraint("cohort_id", "course_id", name="uq_cohort_curriculum_cohort_course"),
        sa.UniqueConstraint("cohort_id", "position", name="uq_cohort_curriculum_cohort_position"),
    )
    op.create_index("ix_cohort_curriculum_cohort_id", "cohort_curriculum", ["cohort_id"])


def downgrade() -> None:
    op.drop_index("ix_cohort_curriculum_cohort_id", table_name="cohort_curriculum")
    op.drop_table("cohort_curriculum")
