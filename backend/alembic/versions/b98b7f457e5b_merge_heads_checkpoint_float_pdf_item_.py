"""merge heads: checkpoint float precision (PR #18) + LMS program pdf item type

Two branches independently resolved the same b18889c4e94d/c4d9e2f6a813
split (9f7be899b2a4 on the checkpoint-float branch, c2a5f9e1b7d4 on this
one) — merging them back together leaves both resolutions as separate
heads. Same shape as the two earlier merge migrations.

Revision ID: b98b7f457e5b
Revises: 9f7be899b2a4, c2a5f9e1b7d4
Create Date: 2026-08-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b98b7f457e5b'
down_revision: Union[str, None] = ('9f7be899b2a4', 'c2a5f9e1b7d4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
