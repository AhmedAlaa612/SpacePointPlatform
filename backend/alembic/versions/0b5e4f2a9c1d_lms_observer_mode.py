"""lms observer mode — assignment mode + observer teams + observer role (2026-10).

"An observer is a student with a label": observers run the identical student
engine, partitioned by `lms_program_assignments.mode` ("participant" |
"observer") and `learner_teams.is_observer`, with `UserRole.observer` and
`SP-OB-####-UAE` cards for pure-observer accounts.

Revision ID: 0b5e4f2a9c1d
Revises: c9d2e5f6a7b8
Create Date: 2026-10-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0b5e4f2a9c1d'
down_revision: Union[str, None] = 'c9d2e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block (same
    # pattern as c7e2b41a0039 'student' and c4f9b25e0015 'coo'/'storekeeper').
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'observer'")

    op.add_column(
        'lms_program_assignments',
        sa.Column('mode', sa.String(16), nullable=False, server_default='participant'),
    )
    op.add_column(
        'learner_teams',
        sa.Column('is_observer', sa.Boolean(), nullable=False, server_default='false'),
    )
    op.create_index('ix_learner_teams_is_observer', 'learner_teams', ['is_observer'])


def downgrade() -> None:
    op.drop_index('ix_learner_teams_is_observer', table_name='learner_teams')
    op.drop_column('learner_teams', 'is_observer')
    op.drop_column('lms_program_assignments', 'mode')
    # Postgres cannot drop a value from an enum type — no-op by design.
