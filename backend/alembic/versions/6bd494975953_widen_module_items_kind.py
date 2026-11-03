"""widen_module_items_kind

Revision ID: 6bd494975953
Revises: 9017f37d67ed
Create Date: 2026-11-03 11:05:34.297221

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6bd494975953'
down_revision: Union[str, None] = '9017f37d67ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('module_items', 'kind', type_=sa.String(32), existing_type=sa.String(10), existing_nullable=False)


def downgrade() -> None:
    op.alter_column('module_items', 'kind', type_=sa.String(10), existing_type=sa.String(32), existing_nullable=False)
