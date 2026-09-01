"""merge heads: learning_paths.access_mode + quiz_question_order

PR #38 and PR #39 both branched off c8e1f9a4d2b6 and each added their own
migration on top of it before either merged, forking the head. No-op merge,
same shape as the repo's existing merge revisions (e.g. 9f7be899b2a4).

Revision ID: fee3a10d9c9b
Revises: e8a85d1c464b, f3a7c1d8e942
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'fee3a10d9c9b'
down_revision: Union[str, None] = ('e8a85d1c464b', 'f3a7c1d8e942')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
