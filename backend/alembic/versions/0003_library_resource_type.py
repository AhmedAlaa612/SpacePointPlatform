"""library_resources: add resource_type column

Old rows (file uploads) had no resource_type column — this adds it with a
server-side default of 'file' so existing rows are correctly classified and
the signed-URL generation path in the list endpoints works for them.

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-27

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "library_resources",
        sa.Column(
            "resource_type",
            sa.String(10),
            nullable=False,
            server_default="file",
        ),
    )


def downgrade() -> None:
    op.drop_column("library_resources", "resource_type")
