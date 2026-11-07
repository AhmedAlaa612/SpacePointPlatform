"""Add excuse_letter_config to cohorts.

Revision ID: fa14d06f0053
Revises: f9a3c95e0052
Create Date: 2026-11-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fa14d06f0053"
down_revision: Union[str, None] = "f9a3c95e0052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "cohorts",
        sa.Column(
            "excuse_letter_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("cohorts", "excuse_letter_config")
