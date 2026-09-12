"""item_datasheets — add datasheet_bucket and datasheet_path to items table.

Revision ID: a1d4f9e20045
Revises: f3b2c1a4e5d6
Create Date: 2026-09-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1d4f9e20045'
down_revision: Union[str, None] = 'f3b2c1a4e5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('items', sa.Column('datasheet_bucket', sa.String(64), nullable=True))
    op.add_column('items', sa.Column('datasheet_path', sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column('items', 'datasheet_path')
    op.drop_column('items', 'datasheet_bucket')
