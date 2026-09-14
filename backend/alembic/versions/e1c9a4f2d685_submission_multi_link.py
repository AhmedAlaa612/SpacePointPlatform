"""submission_multi_link — multiple labeled links per submission (2026-09-14)

Client ask: allow a `submission` checklist item to take several links at
once, each with an optional label (e.g. "Member 1 link", "Member 2 link",
"Team link" all in one submission), ops-controlled per item.

- `lms_program_items.submission_multi_link`: the per-item toggle, off by
  default so every existing item keeps its current one-link behavior.
- `lms_program_item_progress.submitted_links` /
  `lms_program_team_item_progress.submitted_links`: the multi-link answer
  itself, `[{"label": str|None, "url": str}, ...]`, NULL for a non-multi
  item. Additive next to the existing `submitted_url` column (left
  untouched) rather than replacing it — a multi-link submission still
  mirrors its first link's url into `submitted_url` at write time (see
  routers/lms/student.py::submit_program_item) so any older reader that
  only knows that column keeps working.

Revision ID: e1c9a4f2d685
Revises: b4f1c8e30a72
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e1c9a4f2d685'
down_revision: Union[str, None] = 'b4f1c8e30a72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'lms_program_items',
        sa.Column('submission_multi_link', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.add_column(
        'lms_program_item_progress',
        sa.Column('submitted_links', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'lms_program_team_item_progress',
        sa.Column('submitted_links', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('lms_program_team_item_progress', 'submitted_links')
    op.drop_column('lms_program_item_progress', 'submitted_links')
    op.drop_column('lms_program_items', 'submission_multi_link')
