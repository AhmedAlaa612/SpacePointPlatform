"""learner_teams_roster_id_ci_name — roster_team_id + case-insensitive
name uniqueness on learner_teams, and contacts.nationality (2026-09-14)

Team onboarding rewrite: a competition roster import will group students by
an external "team id" rather than a team name (the name may not exist yet
— students set it themselves after onboarding, deadline-gated). See
app/models/team.py's module docstring for the full reasoning.

- `learner_teams.roster_team_id`: the import's grouping key, nullable
  (every pre-existing team gets NULL — it was never created through this
  path). `UNIQUE(cohort_id, roster_team_id)` makes a re-imported sheet
  idempotent.
- Name uniqueness moves from a plain `UNIQUE(cohort_id, name)` constraint
  to a case-insensitive `lower(name)` expression index — "Team" and "team"
  must not both be claimable in the same cohort. Pre-flight check below
  refuses to run if any existing cohort already has two teams whose names
  collide case-insensitively (never expected in practice, but a migration
  must fail loudly rather than silently corrupt).
- `contacts.nationality`: new informational column, same posture as the
  existing `grade` column — see app/models/spine/contact.py.

Revision ID: b4f1c8e30a72
Revises: a8c4e1b906f3
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b4f1c8e30a72'
down_revision: Union[str, None] = 'a8c4e1b906f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    collision = conn.execute(sa.text(
        "SELECT cohort_id, lower(name) FROM learner_teams "
        "WHERE cohort_id IS NOT NULL GROUP BY cohort_id, lower(name) HAVING count(*) > 1 LIMIT 1"
    )).first()
    if collision is not None:
        raise RuntimeError(
            f"Refusing to migrate: cohort {collision[0]} already has two teams whose names collide "
            f"case-insensitively ('{collision[1]}') — resolve manually before re-running this migration."
        )

    op.add_column('contacts', sa.Column('nationality', sa.String(length=64), nullable=True))

    op.add_column('learner_teams', sa.Column('roster_team_id', sa.String(length=64), nullable=True))
    op.alter_column('learner_teams', 'name', type_=sa.String(length=100), existing_type=sa.String(length=80))

    op.drop_constraint('uq_learner_teams_cohort_name', 'learner_teams', type_='unique')
    op.create_index(
        'ix_learner_teams_cohort_name_ci', 'learner_teams',
        ['cohort_id', sa.text('lower(name)')], unique=True,
    )
    op.create_unique_constraint(
        'uq_learner_teams_cohort_roster_team_id', 'learner_teams', ['cohort_id', 'roster_team_id'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_learner_teams_cohort_roster_team_id', 'learner_teams', type_='unique')
    op.drop_index('ix_learner_teams_cohort_name_ci', table_name='learner_teams')
    op.create_unique_constraint('uq_learner_teams_cohort_name', 'learner_teams', ['cohort_id', 'name'])

    op.alter_column('learner_teams', 'name', type_=sa.String(length=80), existing_type=sa.String(length=100))
    op.drop_column('learner_teams', 'roster_team_id')

    op.drop_column('contacts', 'nationality')
