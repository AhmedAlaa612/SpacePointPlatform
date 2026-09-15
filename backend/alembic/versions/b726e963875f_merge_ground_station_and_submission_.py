"""merge ground_station and submission_link_labels heads

Revision ID: b726e963875f
Revises: cacc3b82a3ee, f1f4a9765e49
Create Date: 2026-09-15 02:32:05.139769

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b726e963875f'
down_revision: Union[str, None] = ('cacc3b82a3ee', 'f1f4a9765e49')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
