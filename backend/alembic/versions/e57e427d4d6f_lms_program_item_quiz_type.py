"""LMS Program checklist `quiz` item type (2026-09) — one additive nullable
FK on `lms_program_items`, same shape as `course_id`/`mission_id`. See
`services/lms/program.py`'s `AUTO_TRACKED_TYPES` and
`app/models/lms/cohort_quiz.py` for how it's read.

Revision ID: e57e427d4d6f
Revises: db541138ef8c
Create Date: 2026-09-09 00:00:00.000001

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e57e427d4d6f'
down_revision: Union[str, None] = 'db541138ef8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'lms_program_items',
        sa.Column(
            'cohort_quiz_template_id', postgresql.UUID(as_uuid=True),
            sa.ForeignKey('cohort_quiz_templates.id', ondelete='RESTRICT'), nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('lms_program_items', 'cohort_quiz_template_id')
