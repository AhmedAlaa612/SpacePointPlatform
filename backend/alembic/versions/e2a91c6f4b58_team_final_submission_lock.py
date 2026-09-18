"""team_final_submission_lock — learner_teams.final_locked_at /
final_locked_by (2026-09) — the "Final Submit" action on a team's
checklist. NULL means still editable (a nullable timestamp doubling as
the boolean, same idiom as LmsProgramItemProgress.completed_at). See
app/models/team.py's Team docstring for the full reasoning, including why
this is deliberately one-way from the team's side (only ops clears it).

Revision ID: e2a91c6f4b58
Revises: a3f7c1e9b284
Create Date: 2026-09-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'e2a91c6f4b58'
down_revision: Union[str, None] = 'a3f7c1e9b284'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('learner_teams', sa.Column('final_locked_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('learner_teams', sa.Column('final_locked_by', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_learner_teams_final_locked_by', 'learner_teams',
        'users', ['final_locked_by'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_learner_teams_final_locked_by', 'learner_teams', type_='foreignkey')
    op.drop_column('learner_teams', 'final_locked_by')
    op.drop_column('learner_teams', 'final_locked_at')
