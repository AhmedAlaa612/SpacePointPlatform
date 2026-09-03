"""LMS Roadmap board (2026-09) — five additive columns on lms_program_items.

Powers the gated visual roadmap redesign of the student checklist
(docs/HANDOFF_LMS.md §11): `mission_step_key` targets one Madar design
phase instead of the whole mission run, `gated` locks a tile until every
earlier non-optional item is done, `guideline_kind`/`guideline_url` back
the task drawer's "view the guideline" step (a PDF reuses the existing
`pdf_path` column/upload, so only link/video need a URL column), and
`checkpoint_label` groups tiles into the board's row sections. No new
tables, no constraint changes — see services/lms/program.py's
`compute_lock_states` and `refresh_item_progress` for how these are read.

Revision ID: a3f6d18c5b02
Revises: fee3a10d9c9b
Create Date: 2026-09-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3f6d18c5b02'
down_revision: Union[str, None] = 'fee3a10d9c9b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('lms_program_items', sa.Column('mission_step_key', sa.String(length=24), nullable=True))
    op.add_column(
        'lms_program_items',
        sa.Column('gated', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column('lms_program_items', sa.Column('guideline_kind', sa.String(length=8), nullable=True))
    op.add_column('lms_program_items', sa.Column('guideline_url', sa.String(length=512), nullable=True))
    op.add_column('lms_program_items', sa.Column('checkpoint_label', sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column('lms_program_items', 'checkpoint_label')
    op.drop_column('lms_program_items', 'guideline_url')
    op.drop_column('lms_program_items', 'guideline_kind')
    op.drop_column('lms_program_items', 'gated')
    op.drop_column('lms_program_items', 'mission_step_key')
