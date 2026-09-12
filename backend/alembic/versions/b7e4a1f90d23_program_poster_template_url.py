"""program_poster_template_url — add poster_template_url to programs and lms_programs.

Revision ID: b7e4a1f90d23
Revises: a1d4f9e20045
Create Date: 2026-09-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7e4a1f90d23'
down_revision: Union[str, None] = 'a1d4f9e20045'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('programs', sa.Column('poster_template_url', sa.String(512), nullable=True))
    op.add_column('lms_programs', sa.Column('poster_template_url', sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column('lms_programs', 'poster_template_url')
    op.drop_column('programs', 'poster_template_url')
