"""merge heads: course certificate opt-out + team mission run shared attempt

Revision ID: a8c4e1b906f3
Revises: d3e8f6c1a927, d7f4b8a1e523
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a8c4e1b906f3'
down_revision: Union[str, None] = ('d3e8f6c1a927', 'd7f4b8a1e523')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
