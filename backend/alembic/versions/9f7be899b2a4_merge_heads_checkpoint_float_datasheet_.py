"""merge heads: checkpoint float precision + datasheet upload + drop price override

Revision ID: 9f7be899b2a4
Revises: a4c1e93f0044, b18889c4e94d, c4d9e2f6a813
Create Date: 2026-08-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9f7be899b2a4'
down_revision: Union[str, None] = ('a4c1e93f0044', 'b18889c4e94d', 'c4d9e2f6a813')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
