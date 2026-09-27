"""add_shop_items_and_orders

Revision ID: c7d3e1f9a2b5
Revises: 2a26344b41c6
Create Date: 2026-09-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c7d3e1f9a2b5'
down_revision: Union[str, None] = '2a26344b41c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Shop Items
    op.create_table(
        'shop_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('item_id', sa.UUID(), nullable=False),
        sa.Column('slug', sa.String(length=128), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('subtitle', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price_aed', sa.Numeric(precision=10, scale=2), server_default='0.00', nullable=False),
        sa.Column('compare_at_price_aed', sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column('cover_image_url', sa.String(length=512), nullable=True),
        sa.Column('gallery_images', postgresql.JSONB(astext_type=sa.Text()), server_default='[]', nullable=False),
        sa.Column('is_published', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_preorder_enabled', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('preorder_message', sa.String(length=255), server_default='Pre-order available — Estimated dispatch within 2-3 weeks', nullable=False),
        sa.Column('display_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['item_id'], ['items.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('item_id'),
        sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_shop_items_id'), 'shop_items', ['id'], unique=False)
    op.create_index(op.f('ix_shop_items_item_id'), 'shop_items', ['item_id'], unique=True)
    op.create_index(op.f('ix_shop_items_slug'), 'shop_items', ['slug'], unique=True)
    op.create_index(op.f('ix_shop_items_is_published'), 'shop_items', ['is_published'], unique=False)

    # 2. Shop Orders
    op.create_table(
        'shop_orders',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('order_number', sa.String(length=32), nullable=False),
        sa.Column('customer_name', sa.String(length=255), nullable=False),
        sa.Column('customer_email', sa.String(length=255), nullable=False),
        sa.Column('customer_phone', sa.String(length=50), nullable=True),
        sa.Column('shipping_address', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='pending_payment', nullable=False),
        sa.Column('order_type', sa.String(length=32), server_default='standard', nullable=False),
        sa.Column('total_amount_aed', sa.Numeric(precision=10, scale=2), server_default='0.00', nullable=False),
        sa.Column('currency', sa.String(length=3), server_default='AED', nullable=False),
        sa.Column('stripe_payment_intent_id', sa.String(length=255), nullable=True),
        sa.Column('stripe_checkout_session_id', sa.String(length=255), nullable=True),
        sa.Column('fulfilled_warehouse_id', sa.UUID(), nullable=True),
        sa.Column('fulfilled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fulfillment_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['fulfilled_warehouse_id'], ['warehouses.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_number')
    )
    op.create_index(op.f('ix_shop_orders_id'), 'shop_orders', ['id'], unique=False)
    op.create_index(op.f('ix_shop_orders_order_number'), 'shop_orders', ['order_number'], unique=True)
    op.create_index(op.f('ix_shop_orders_customer_email'), 'shop_orders', ['customer_email'], unique=False)
    op.create_index(op.f('ix_shop_orders_status'), 'shop_orders', ['status'], unique=False)
    op.create_index(op.f('ix_shop_orders_stripe_checkout_session_id'), 'shop_orders', ['stripe_checkout_session_id'], unique=False)
    op.create_index(op.f('ix_shop_orders_stripe_payment_intent_id'), 'shop_orders', ['stripe_payment_intent_id'], unique=False)
    op.create_index(op.f('ix_shop_orders_created_at'), 'shop_orders', ['created_at'], unique=False)

    # 3. Shop Order Items
    op.create_table(
        'shop_order_items',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=False),
        sa.Column('shop_item_id', sa.UUID(), nullable=False),
        sa.Column('item_name', sa.String(length=255), nullable=False),
        sa.Column('unit_price_aed', sa.Numeric(precision=10, scale=2), server_default='0.00', nullable=False),
        sa.Column('quantity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('is_preorder', sa.Boolean(), server_default='false', nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['shop_orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['shop_item_id'], ['shop_items.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_shop_order_items_id'), 'shop_order_items', ['id'], unique=False)
    op.create_index(op.f('ix_shop_order_items_order_id'), 'shop_order_items', ['order_id'], unique=False)


def downgrade() -> None:
    op.drop_table('shop_order_items')
    op.drop_table('shop_orders')
    op.drop_table('shop_items')
