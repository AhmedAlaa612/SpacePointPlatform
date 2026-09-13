"""program_default_assessment_config — programs.default_assessment_config_id
(2026-09-13) — a program-level default, copied into a new cohort's own
`AssessmentCohortAssignment` once at creation. See `Program`'s and
`ProgramOpening`'s docstrings for why this is a copy, not a live link.

Revision ID: c9f4e1a68d75
Revises: b7e4a1f90d23
Create Date: 2026-09-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'c9f4e1a68d75'
down_revision: Union[str, None] = 'b7e4a1f90d23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'programs',
        sa.Column('default_assessment_config_id', UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_programs_default_assessment_config_id', 'programs', 'assessment_configs',
        ['default_assessment_config_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_programs_default_assessment_config_id', 'programs', type_='foreignkey')
    op.drop_column('programs', 'default_assessment_config_id')
