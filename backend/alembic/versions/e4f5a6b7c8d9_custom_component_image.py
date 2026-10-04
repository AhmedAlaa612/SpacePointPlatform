"""add image_bucket and image_path to design_custom_components

Revision ID: e4f5a6b7c8d9
Revises: 0b5e4f2a9c1d
Create Date: 2026-10-04 20:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'e4f5a6b7c8d9'
down_revision = '0b5e4f2a9c1d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'design_custom_components',
        sa.Column('image_bucket', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'design_custom_components',
        sa.Column('image_path', sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('design_custom_components', 'image_path')
    op.drop_column('design_custom_components', 'image_bucket')
