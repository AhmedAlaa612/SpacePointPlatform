"""Add sub_item_proofs JSONB map to instructor and ops checklist progress tables.

Revision ID: bb22cc33dd44
Revises: aa11bb22cc33
Create Date: 2026-11-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "bb22cc33dd44"
down_revision: Union[str, None] = "aa11bb22cc33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "instructor_checklist_progress",
        sa.Column(
            "sub_item_proofs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "session_ops_checklist_progress",
        sa.Column(
            "sub_item_proofs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("session_ops_checklist_progress", "sub_item_proofs")
    op.drop_column("instructor_checklist_progress", "sub_item_proofs")
