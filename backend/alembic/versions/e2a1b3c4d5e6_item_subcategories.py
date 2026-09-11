"""item_subcategories — add subcategories table and items.subcategory column.

Revision ID: e2a1b3c4d5e6
Revises: b2d5e7f10a84
Create Date: 2026-09-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e2a1b3c4d5e6'
down_revision: Union[str, None] = 'b2d5e7f10a84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'item_subcategories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('item_categories.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('category_id', 'name', name='uq_item_subcategories_category_name'),
    )
    op.create_index('ix_item_subcategories_category_id', 'item_subcategories', ['category_id'])

    op.add_column('items', sa.Column('subcategory', sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column('items', 'subcategory')
    op.drop_index('ix_item_subcategories_category_id', table_name='item_subcategories')
    op.drop_table('item_subcategories')
