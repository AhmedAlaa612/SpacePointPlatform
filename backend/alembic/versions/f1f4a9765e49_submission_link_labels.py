"""submission_link_labels — ops's own fixed label set (2026-09-14)

Client ask: on a `submission_multi_link` item, ops should set the labels
themselves (e.g. "Member 1 link", "Member 2 link", "Team link") instead of
students typing free-text labels, and mark each label required or optional
via a checkbox — ops decides which slots block submission.

`lms_program_items.submission_link_labels`: `[{"label": str, "required":
bool}, ...]`, in the order ops entered them. NULL for a non-multi-link
item, or for a multi-link item authored before this existed — that older
shape (free-text, student-entered labels, none required) still works
unchanged (see routers/lms/student.py::submit_program_item and
LmsProgramItem.submission_link_labels's own comment).

Revision ID: f1f4a9765e49
Revises: e1c9a4f2d685
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f1f4a9765e49'
down_revision: Union[str, None] = 'e1c9a4f2d685'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'lms_program_items',
        sa.Column('submission_link_labels', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('lms_program_items', 'submission_link_labels')
