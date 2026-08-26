"""video checkpoints — start/end seconds to float, for h:m:s:ms precision

The authoring UI now lets operators place a checkpoint to the millisecond
(h:m:s:ms) instead of only whole seconds, so `start_seconds`/`end_seconds`
need sub-second precision in storage too.

Revision ID: a4c1e93f0044
Revises: 94eaeb5ddbde
Create Date: 2026-08-24
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a4c1e93f0044"
down_revision = "94eaeb5ddbde"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "video_checkpoints", "start_seconds",
        existing_type=sa.Integer(), type_=sa.Float(), nullable=False,
    )
    op.alter_column(
        "video_checkpoints", "end_seconds",
        existing_type=sa.Integer(), type_=sa.Float(), nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "video_checkpoints", "end_seconds",
        existing_type=sa.Float(), type_=sa.Integer(), nullable=True,
    )
    op.alter_column(
        "video_checkpoints", "start_seconds",
        existing_type=sa.Float(), type_=sa.Integer(), nullable=False,
    )
