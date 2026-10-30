"""submission_table_config — tabular grid submission format (2026-10-30)

Supports structured tabular submissions on LMS checklist items (individual or team),
allowing ops to define a tag column (with preset tags) and arbitrary custom columns
(link, text, select dropdown).

- `lms_program_items.submission_table_config`: JSONB holding tag_label, tags,
  allow_custom_tags, and column specifications.

Revision ID: a7c9e1f3b5d2
Revises: d8e4f2a1b9c3
Create Date: 2026-10-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a7c9e1f3b5d2'
down_revision: Union[str, None] = 'd8e4f2a1b9c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'lms_program_items',
        sa.Column('submission_table_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('lms_program_items', 'submission_table_config')
