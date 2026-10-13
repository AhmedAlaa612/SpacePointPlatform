"""add keep_course_access_after_completion to programs and cohorts (2026-10)

Revision ID: e1e2f3a4b5c7
Revises: c9d4e5f60011
"""

import sqlalchemy as sa
from alembic import op

revision = "e1e2f3a4b5c7"
down_revision = "c9d4e5f60011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "programs",
        sa.Column(
            "keep_course_access_after_completion",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "cohorts",
        sa.Column(
            "keep_course_access_after_completion",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("cohorts", "keep_course_access_after_completion")
    op.drop_column("programs", "keep_course_access_after_completion")
