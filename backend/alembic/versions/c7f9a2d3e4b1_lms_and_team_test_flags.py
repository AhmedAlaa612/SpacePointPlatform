"""Add is_test flag to lms_program_assignments and learner_teams.

Revision ID: c7f9a2d3e4b1
Revises: b2d5e7f10a84
Create Date: 2026-09-11 18:52:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7f9a2d3e4b1'
down_revision: Union[str, None] = 'b2d5e7f10a84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'lms_program_assignments',
        sa.Column('is_test', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.add_column(
        'learner_teams',
        sa.Column('is_test', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )


def downgrade() -> None:
    op.drop_column('learner_teams', 'is_test')
    op.drop_column('lms_program_assignments', 'is_test')
