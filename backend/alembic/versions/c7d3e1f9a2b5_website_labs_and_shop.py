"""website labs and shop

Revision ID: c7d3e1f9a2b5
Revises: b6c7d8e9f0a1
Create Date: 2026-10-09

Step 7 — SpacePoint Labs R&D Sync & Ground Station Shop Stripe Activation:
creates `website_labs_projects`, `shop_items`, `shop_orders`, and
`shop_order_items`, seeding the Miura-Ori project plus the six flagship
Ground Station products (only when each table is empty).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = 'c7d3e1f9a2b5'
down_revision = 'b6c7d8e9f0a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'website_labs_projects',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=128), nullable=False),
        sa.Column('badges', JSONB(), nullable=False, server_default='[]'),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('project_url', sa.String(length=512), nullable=False, server_default='/miura-ori'),
        sa.Column('cta_label', sa.String(length=128), nullable=False, server_default='Launch Project →'),
        sa.Column('cover_image_url', sa.String(length=512), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_index('ix_website_labs_projects_slug', 'website_labs_projects', ['slug'], unique=True)
    op.create_index('ix_website_labs_projects_is_active', 'website_labs_projects', ['is_active'])

    op.create_table(
        'shop_items',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('item_id', UUID(as_uuid=True), sa.ForeignKey('items.id', ondelete='SET NULL'), nullable=True),
        sa.Column('slug', sa.String(length=128), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('subtitle', sa.String(length=255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('price_aed', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('compare_at_price_aed', sa.Numeric(10, 2), nullable=True),
        sa.Column('cover_image_url', sa.String(length=512), nullable=True),
        sa.Column('gallery_images', JSONB(), nullable=False, server_default='[]'),
        sa.Column('is_published', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_preorder_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column(
            'preorder_message', sa.String(length=255), nullable=False,
            server_default='Pre-order available — Estimated dispatch within 2-3 weeks',
        ),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_index('ix_shop_items_slug', 'shop_items', ['slug'], unique=True)
    op.create_index('ix_shop_items_is_published', 'shop_items', ['is_published'])

    op.create_table(
        'shop_orders',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('order_number', sa.String(length=32), nullable=False),
        sa.Column('customer_name', sa.String(length=255), nullable=False),
        sa.Column('customer_email', sa.String(length=255), nullable=False),
        sa.Column('customer_phone', sa.String(length=50), nullable=True),
        sa.Column('shipping_address', JSONB(), nullable=False, server_default='{}'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='pending_payment'),
        sa.Column('order_type', sa.String(length=32), nullable=False, server_default='standard'),
        sa.Column('total_amount_aed', sa.Numeric(10, 2), nullable=False, server_default='0.00'),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='AED'),
        sa.Column('stripe_payment_intent_id', sa.String(length=255), nullable=True),
        sa.Column('stripe_checkout_session_id', sa.String(length=255), nullable=True),
        sa.Column('fulfilled_warehouse_id', UUID(as_uuid=True), sa.ForeignKey('warehouses.id', ondelete='SET NULL'), nullable=True),
        sa.Column('fulfilled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fulfillment_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_number'),
    )

    op.create_table(
        'shop_order_items',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('order_id', UUID(as_uuid=True), sa.ForeignKey('shop_orders.id', ondelete='CASCADE'), nullable=False),
        sa.Column('shop_item_id', UUID(as_uuid=True), sa.ForeignKey('shop_items.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('item_name', sa.String(length=255), nullable=False),
        sa.Column('unit_price_aed', sa.Numeric(10, 2), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_preorder', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_shop_order_items_order_id', 'shop_order_items', ['order_id'])

    conn = op.get_bind()
    conn.execute(sa.text(
        """
        INSERT INTO website_labs_projects
            (id, title, slug, badges, description, project_url, cta_label, display_order, is_active)
        SELECT * FROM (VALUES
            (
                '50000000-0000-4000-8000-000000000001'::uuid, 'Miura-Ori Solar Array', 'miura-ori-solar-array',
                '["Active Simulation", "Deployable Origami Mechanics"]'::jsonb,
                'Origami mathematics applied to high-area solar arrays for nanosatellites and deep space probes. Interactive 3D deployable simulation with kinematic fold studies.',
                '/miura-ori', 'Launch Project →', 1, true
            )
        ) AS seed(id, title, slug, badges, description, project_url, cta_label, display_order, is_active)
        WHERE NOT EXISTS (SELECT 1 FROM website_labs_projects)
        """
    ))
    conn.execute(sa.text(
        """
        INSERT INTO shop_items
            (id, slug, display_name, price_aed, cover_image_url,
             subtitle, description, is_published, display_order)
        SELECT * FROM (VALUES
            (
                '50000000-0000-4000-8000-000000000011'::uuid, 'keychain',
                'Remove Before Launch Key Chain', 20.00,
                '/assets/img/Products photos/Keychain Front side.png',
                'Merchandise · Everyday Explorer Gear',
                'Classic flight-ready red woven tag with embroidered SpacePoint insignia for your everyday keys.',
                true, 1
            ),
            (
                '50000000-0000-4000-8000-000000000012'::uuid, 'minisat-explorer',
                'MiniSat Explorer', 30.00,
                '/assets/img/Products photos/MiniCubeSat.png',
                'Models · 1:4 Precision Scale Replica',
                'A precision 1:4 scale miniature 1U CubeSat model with detailed solar cell engravings and antenna array.',
                true, 2
            ),
            (
                '50000000-0000-4000-8000-000000000013'::uuid, 'zero-gravity-fit',
                'Zero Gravity Fit', 100.00,
                '/assets/img/Products photos/T-Shirt.png',
                'Apparel · 100% Organic Heavyweight Cotton',
                'Heavyweight 100% organic cotton t-shirt with signature SpacePoint constellation back-print and aerospace typography.',
                true, 3
            ),
            (
                '50000000-0000-4000-8000-000000000014'::uuid, 'mpkit',
                'MPKit - Train Like Space Engineer', 2000.00,
                '/assets/img/Products photos/MPKit First Side.png',
                'Hardware · Complete Hands-on Satellite Kit',
                'The complete hands-on aerospace educational kit: EPS board, OBC microcontroller, telemetry radio, and sensors.',
                true, 4
            ),
            (
                '50000000-0000-4000-8000-000000000015'::uuid, 'spacepoint-cap',
                'SpacePoint Cap', 75.00,
                '/assets/img/Products photos/Cap.png',
                'Apparel · Structured Six-Panel Obsidian Cap',
                'Structured six-panel cap in matte obsidian with high-density embroidered SpacePoint badge and adjustable strap.',
                true, 5
            ),
            (
                '50000000-0000-4000-8000-000000000016'::uuid, 'phone-metal-sticker',
                'Phone Metal Sticker', 20.00,
                '/assets/img/Products photos/Mission Mark.png',
                'Merchandise · Electroplated Metal Insignia',
                'Ultra-thin electroplated metal sticker for phones and laptops featuring the SpacePoint aerospace insignia.',
                true, 6
            )
        ) AS seed(id, slug, display_name, price_aed, cover_image_url,
                  subtitle, description, is_published, display_order)
        WHERE NOT EXISTS (SELECT 1 FROM shop_items)
        """
    ))


def downgrade() -> None:
    op.drop_index('ix_shop_order_items_order_id', table_name='shop_order_items')
    op.drop_table('shop_order_items')
    op.drop_table('shop_orders')
    op.drop_index('ix_shop_items_is_published', table_name='shop_items')
    op.drop_index('ix_shop_items_slug', table_name='shop_items')
    op.drop_table('shop_items')
    op.drop_index('ix_website_labs_projects_is_active', table_name='website_labs_projects')
    op.drop_index('ix_website_labs_projects_slug', table_name='website_labs_projects')
    op.drop_table('website_labs_projects')
