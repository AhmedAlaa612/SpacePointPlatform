"""add visibility_settings to competition_result_publications

Revision ID: a1b2c3d4e5f7
Revises: 81a9c3d4e5f6
Create Date: 2026-10-03 00:15:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f7'
down_revision = '81a9c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'competition_result_publications',
        sa.Column('visibility_settings', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False)
    )


def downgrade():
    op.drop_column('competition_result_publications', 'visibility_settings')
