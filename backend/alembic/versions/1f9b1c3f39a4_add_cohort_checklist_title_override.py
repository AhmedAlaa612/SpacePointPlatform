"""add_cohort_checklist_title_override

Revision ID: 1f9b1c3f39a4
Revises: d7a1c92d0048
Create Date: 2026-09-22 23:50:24.513891

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '1f9b1c3f39a4'
down_revision: Union[str, None] = 'd7a1c92d0048'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cohorts', sa.Column('checklist_title_override', sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column('cohorts', 'checklist_title_override')
