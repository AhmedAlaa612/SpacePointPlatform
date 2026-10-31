"""warehouse_boxes_and_multi_placement — add warehouse boxes and update item cabin assignments.

Revision ID: c9e1f2a3b4d5
Revises: b8d1e2f3a4c5
Create Date: 2026-10-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c9e1f2a3b4d5'
down_revision: Union[str, None] = 'b8d1e2f3a4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add image fields to warehouse_cabins
    op.add_column('warehouse_cabins', sa.Column('image_bucket', sa.String(64), nullable=True))
    op.add_column('warehouse_cabins', sa.Column('image_path', sa.String(255), nullable=True))

    # 2. Create warehouse_boxes
    op.create_table(
        'warehouse_boxes',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('warehouse_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('warehouses.id', ondelete='CASCADE'), nullable=False),
        sa.Column('cabin_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('warehouse_cabins.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(64), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('image_bucket', sa.String(64), nullable=True),
        sa.Column('image_path', sa.String(255), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('cabin_id', 'name', name='uq_warehouse_boxes_cabin_name'),
    )
    op.create_index('ix_warehouse_boxes_warehouse_id', 'warehouse_boxes', ['warehouse_id'])
    op.create_index('ix_warehouse_boxes_cabin_id', 'warehouse_boxes', ['cabin_id'])

    # 3. Update item_cabin_assignments for boxes and multi-placement
    op.drop_constraint('uq_item_cabin_assignments_warehouse_item', 'item_cabin_assignments', type_='unique')
    op.add_column('item_cabin_assignments', sa.Column('box_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('warehouse_boxes.id', ondelete='CASCADE'), nullable=True))
    op.create_index('ix_item_cabin_assignments_box_id', 'item_cabin_assignments', ['box_id'])

    # Unique index for loose items: one loose placement per (warehouse, cabin, item) when box_id is NULL
    op.create_index(
        'uq_item_cabin_loose',
        'item_cabin_assignments',
        ['warehouse_id', 'cabin_id', 'item_id'],
        unique=True,
        postgresql_where=sa.text('box_id IS NULL'),
    )

    # Unique index for boxed items: one placement per (warehouse, box, item) when box_id is NOT NULL
    op.create_index(
        'uq_item_cabin_boxed',
        'item_cabin_assignments',
        ['warehouse_id', 'box_id', 'item_id'],
        unique=True,
        postgresql_where=sa.text('box_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_item_cabin_boxed', table_name='item_cabin_assignments')
    op.drop_index('uq_item_cabin_loose', table_name='item_cabin_assignments')
    op.drop_index('ix_item_cabin_assignments_box_id', table_name='item_cabin_assignments')
    op.drop_column('item_cabin_assignments', 'box_id')
    op.create_unique_constraint('uq_item_cabin_assignments_warehouse_item', 'item_cabin_assignments', ['warehouse_id', 'item_id'])

    op.drop_index('ix_warehouse_boxes_cabin_id', table_name='warehouse_boxes')
    op.drop_index('ix_warehouse_boxes_warehouse_id', table_name='warehouse_boxes')
    op.drop_table('warehouse_boxes')

    op.drop_column('warehouse_cabins', 'image_path')
    op.drop_column('warehouse_cabins', 'image_bucket')
