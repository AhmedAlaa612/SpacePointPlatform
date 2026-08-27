"""inventory approval policies and requests

Revision ID: e9a39df5fcc0
Revises: c7d2e8a94f5b
Create Date: 2026-08-27 11:05:18.036755

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e9a39df5fcc0'
down_revision: Union[str, None] = 'c7d2e8a94f5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Every action type the approval gate currently knows about — kept here (not
# imported from app code) so this migration reads the same years from now as
# it does today. Seeded at `requires_approval=False`: deploying this feature
# must not start gating anything until the COO turns a gate on herself.
_ACTION_TYPES = ["kit.move", "merch.issue", "merch.return", "stock.adjust"]


def upgrade() -> None:
    op.create_table(
        'inventory_action_policies',
        sa.Column('action_type', sa.String(length=64), nullable=False),
        sa.Column('requires_approval', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('updated_by', sa.UUID(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('action_type'),
    )
    op.create_table(
        'inventory_approval_requests',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('action_type', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), server_default='pending', nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('requested_by', sa.UUID(), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewed_by', sa.UUID(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_inventory_approval_requests_action_type'),
        'inventory_approval_requests', ['action_type'], unique=False,
    )
    op.create_index(
        op.f('ix_inventory_approval_requests_status'),
        'inventory_approval_requests', ['status'], unique=False,
    )

    policies = sa.table(
        'inventory_action_policies',
        sa.column('action_type', sa.String),
        sa.column('requires_approval', sa.Boolean),
    )
    op.bulk_insert(policies, [{'action_type': t, 'requires_approval': False} for t in _ACTION_TYPES])


def downgrade() -> None:
    op.drop_index(op.f('ix_inventory_approval_requests_status'), table_name='inventory_approval_requests')
    op.drop_index(op.f('ix_inventory_approval_requests_action_type'), table_name='inventory_approval_requests')
    op.drop_table('inventory_approval_requests')
    op.drop_table('inventory_action_policies')
