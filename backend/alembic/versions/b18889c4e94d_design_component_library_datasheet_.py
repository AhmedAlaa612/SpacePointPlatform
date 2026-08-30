"""design component library datasheet upload

Revision ID: b18889c4e94d
Revises: c7d2e8a94f5b
Create Date: 2026-08-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b18889c4e94d'
down_revision: Union[str, None] = 'c7d2e8a94f5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('design_component_library', sa.Column('datasheet_bucket', sa.String(length=64), nullable=True))
    op.add_column('design_component_library', sa.Column('datasheet_path', sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column('design_component_library', 'datasheet_path')
    op.drop_column('design_component_library', 'datasheet_bucket')
