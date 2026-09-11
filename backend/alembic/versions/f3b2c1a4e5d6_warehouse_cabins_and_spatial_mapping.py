"""warehouse_cabins_and_spatial_mapping — add warehouse cabins and item cabin assignments.

Revision ID: f3b2c1a4e5d6
Revises: e2a1b3c4d5e6
Create Date: 2026-09-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f3b2c1a4e5d6'
down_revision: Union[str, None] = 'e2a1b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add image fields to warehouses
    op.add_column('warehouses', sa.Column('image_bucket', sa.String(64), nullable=True))
    op.add_column('warehouses', sa.Column('image_path', sa.String(255), nullable=True))

    # 2. Create warehouse_cabins
    op.create_table(
        'warehouse_cabins',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('warehouse_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('warehouses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('pin_x', sa.Float(), nullable=True),
        sa.Column('pin_y', sa.Float(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('warehouse_id', 'name', name='uq_warehouse_cabins_warehouse_name'),
    )
    op.create_index('ix_warehouse_cabins_warehouse_id', 'warehouse_cabins', ['warehouse_id'])

    # 3. Create item_cabin_assignments
    op.create_table(
        'item_cabin_assignments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('warehouse_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('warehouses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('cabin_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('warehouse_cabins.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('qty', sa.Integer(), nullable=True),
        sa.Column('notes', sa.String(128), nullable=True),
        sa.Column('is_primary', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('cabin_id', 'item_id', name='uq_item_cabin_assignments_cabin_item'),
    )
    op.create_index('ix_item_cabin_assignments_warehouse_id', 'item_cabin_assignments', ['warehouse_id'])
    op.create_index('ix_item_cabin_assignments_cabin_id', 'item_cabin_assignments', ['cabin_id'])
    op.create_index('ix_item_cabin_assignments_item_id', 'item_cabin_assignments', ['item_id'])


def downgrade() -> None:
    op.drop_index('ix_item_cabin_assignments_item_id', table_name='item_cabin_assignments')
    op.drop_index('ix_item_cabin_assignments_cabin_id', table_name='item_cabin_assignments')
    op.drop_index('ix_item_cabin_assignments_warehouse_id', table_name='item_cabin_assignments')
    op.drop_table('item_cabin_assignments')

    op.drop_index('ix_warehouse_cabins_warehouse_id', table_name='warehouse_cabins')
    op.drop_table('warehouse_cabins')

    op.drop_column('warehouses', 'image_path')
    op.drop_column('warehouses', 'image_bucket')
