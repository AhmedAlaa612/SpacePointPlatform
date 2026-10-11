"""add contacts.gender column

Revision ID: d8e2f4a6b9c0
Revises: c7d3e1f9a2b5
Create Date: 2026-10-11

Adds informational `gender` column (`String(32)`, nullable) on `contacts`
to support competition roster imports ("Gender" column) and cohort
registration filtering by student gender.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'd8e2f4a6b9c0'
down_revision: Union[str, None] = 'c7d3e1f9a2b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('contacts', sa.Column('gender', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('contacts', 'gender')
