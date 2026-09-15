"""submission_field_type — single-field submission can be text, not just link (2026-09-16)

Client ask: the multi-field toggle (submission_link_labels) already lets a
field be link-or-text, but a plain (non-multi) submission item — the common
case — had no such choice at all, hardcoded to a link paste-back.

- `lms_program_items.submission_field_type`: "link" (default) or "text" —
  only meaningful when submission_multi_link is False; a multi-link item
  picks its type per field instead (submission_link_labels). Defaults to
  "link" so every submission item authored before this existed (the only
  kind there was) is unaffected.
- `lms_program_item_progress.submitted_text` / `lms_program_team_item_
  progress.submitted_text`: the single-field text answer, NULL for a
  link-type or multi-link item. Additive next to the existing
  submitted_url column (left untouched) — exactly one of the two is ever
  populated for a non-multi-link item, matching submission_field_type.

Revision ID: a3f7c1e9b284
Revises: 256962fbd6e0
Create Date: 2026-09-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3f7c1e9b284'
down_revision: Union[str, None] = '256962fbd6e0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'lms_program_items',
        sa.Column('submission_field_type', sa.String(length=8), nullable=False, server_default='link'),
    )
    op.add_column('lms_program_item_progress', sa.Column('submitted_text', sa.Text(), nullable=True))
    op.add_column('lms_program_team_item_progress', sa.Column('submitted_text', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('lms_program_team_item_progress', 'submitted_text')
    op.drop_column('lms_program_item_progress', 'submitted_text')
    op.drop_column('lms_program_items', 'submission_field_type')
