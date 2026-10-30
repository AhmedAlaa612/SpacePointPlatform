"""add sub_items to delivery checklists

Revision ID: b8d1e2f3a4c5
Revises: a7c9e1f3b5d2
Create Date: 2026-10-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b8d1e2f3a4c5'
down_revision: Union[str, None] = 'a7c9e1f3b5d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'delivery_checklist_items',
        sa.Column('sub_items', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
    )
    op.add_column(
        'instructor_checklist_progress',
        sa.Column('completed_sub_items', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
    )
    op.add_column(
        'session_ops_checklist_progress',
        sa.Column('completed_sub_items', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('session_ops_checklist_progress', 'completed_sub_items')
    op.drop_column('instructor_checklist_progress', 'completed_sub_items')
    op.drop_column('delivery_checklist_items', 'sub_items')
