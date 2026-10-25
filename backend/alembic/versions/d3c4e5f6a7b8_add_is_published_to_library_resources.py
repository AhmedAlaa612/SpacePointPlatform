"""Add is_published to library_resources.

Revision ID: d3c4e5f6a7b8
Revises: c2b3d4e5f6a7
Create Date: 2026-10-25 19:16:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d3c4e5f6a7b8"
down_revision: Union[str, None] = "c2b3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "library_resources",
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("library_resources", "is_published")
