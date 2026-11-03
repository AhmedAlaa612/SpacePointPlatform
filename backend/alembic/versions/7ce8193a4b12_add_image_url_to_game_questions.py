"""add_image_url_to_game_questions

Revision ID: 7ce8193a4b12
Revises: 6bd494975953
Create Date: 2026-11-03 23:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ce8193a4b12'
down_revision: Union[str, None] = '6bd494975953'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('game_questions', sa.Column('image_url', sa.String(length=512), nullable=True))
    op.add_column('game_session_questions', sa.Column('image_url', sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column('game_session_questions', 'image_url')
    op.drop_column('game_questions', 'image_url')
