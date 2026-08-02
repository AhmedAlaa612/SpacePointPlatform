"""merge heads: student_completion/workshop_delivery seeds + cohort staffing calls

Revision ID: b88f272265ef
Revises: e1b3d05f0036, e7c4a92d0036
Create Date: 2026-08-01 18:56:09.779008

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b88f272265ef'
down_revision: Union[str, None] = ('e1b3d05f0036', 'e7c4a92d0036')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
