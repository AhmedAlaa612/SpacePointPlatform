"""Add cohort_lms_editors table for granting instructors LMS edit access.

Revision ID: f8a2c94e0051
Revises: f7a1c93b0050
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f8a2c94e0051"
down_revision: Union[str, None] = "f7a1c93b0050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cohort_lms_editors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cohort_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cohorts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "cohort_id", "user_id", name="uq_cohort_lms_editors_cohort_user"
        ),
    )
    op.create_index(
        "ix_cohort_lms_editors_cohort_id", "cohort_lms_editors", ["cohort_id"]
    )
    op.create_index(
        "ix_cohort_lms_editors_user_id", "cohort_lms_editors", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_cohort_lms_editors_user_id", table_name="cohort_lms_editors")
    op.drop_index("ix_cohort_lms_editors_cohort_id", table_name="cohort_lms_editors")
    op.drop_table("cohort_lms_editors")
