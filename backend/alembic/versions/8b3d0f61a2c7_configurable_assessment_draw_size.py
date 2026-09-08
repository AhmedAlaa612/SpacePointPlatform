"""Configurable assessment draw size / critical floor

The 15-question draw and the floor of 3 critical questions were a hardcoded
module constant (`DRAW_SIZE`/`CRITICAL_FLOOR` in
services/instructor_assessment/attempts.py) — fine while there was one bank,
but a second config for a different curriculum may want a shorter quiz or a
different critical mix. Moves both onto `AssessmentConfig` itself, defaulted
to the existing hardcoded values so every config that predates this column
(including the seeded Shallow Flight bank) behaves exactly as it did before.

Revision ID: 8b3d0f61a2c7
Revises: 242a51df6998
Create Date: 2026-09-08
"""

import sqlalchemy as sa
from alembic import op

revision = "8b3d0f61a2c7"
down_revision = "242a51df6998"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_configs",
        sa.Column("draw_size", sa.Integer(), nullable=False, server_default="15"),
    )
    op.add_column(
        "assessment_configs",
        sa.Column("critical_floor", sa.Integer(), nullable=False, server_default="3"),
    )


def downgrade() -> None:
    op.drop_column("assessment_configs", "critical_floor")
    op.drop_column("assessment_configs", "draw_size")
