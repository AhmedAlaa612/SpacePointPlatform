"""add attachments to delivery_checklist_items

Revision ID: e4d5c6b7a8f9
Revises: d3c4e5f6a7b8
Create Date: 2026-10-25 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e4d5c6b7a8f9'
down_revision = 'd3c4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'delivery_checklist_items',
        sa.Column('attachments', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]')
    )

    # Backfill existing material_id and link_url into attachments array
    op.execute("""
        UPDATE delivery_checklist_items
        SET attachments = (
            CASE
                WHEN material_id IS NOT NULL AND link_url IS NOT NULL AND link_url != '' THEN
                    jsonb_build_array(
                        jsonb_build_object('type', 'material', 'material_id', material_id::text),
                        jsonb_build_object('type', 'link', 'url', link_url, 'title', link_url)
                    )
                WHEN material_id IS NOT NULL THEN
                    jsonb_build_array(
                        jsonb_build_object('type', 'material', 'material_id', material_id::text)
                    )
                WHEN link_url IS NOT NULL AND link_url != '' THEN
                    jsonb_build_array(
                        jsonb_build_object('type', 'link', 'url', link_url, 'title', link_url)
                    )
                ELSE '[]'::jsonb
            END
        )
        WHERE (material_id IS NOT NULL OR (link_url IS NOT NULL AND link_url != ''))
    """)


def downgrade():
    op.drop_column('delivery_checklist_items', 'attachments')
