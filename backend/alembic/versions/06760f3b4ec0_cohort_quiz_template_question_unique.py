"""Cohort quiz template questions — unique (template_id, question_id)
(2026-09). Backstops `services/lms/cohort_quiz.py::add_template_question`'s
check-then-insert against a genuine race (two requests adding the same
question to the same template at once) — a DB constraint, not just the
application-level SELECT-then-INSERT check.

Revision ID: 06760f3b4ec0
Revises: e57e427d4d6f
Create Date: 2026-09-09 00:00:00.000002

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '06760f3b4ec0'
down_revision: Union[str, None] = 'e57e427d4d6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_cohort_quiz_template_question_unique', 'cohort_quiz_template_questions', ['template_id', 'question_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_cohort_quiz_template_question_unique', 'cohort_quiz_template_questions', type_='unique')
