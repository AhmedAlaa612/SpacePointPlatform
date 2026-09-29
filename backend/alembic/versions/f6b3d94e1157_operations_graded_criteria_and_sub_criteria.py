"""operations-graded criteria and sub-criteria (2026-09-30)

- `competition_rubric_criteria.scored_by` ('judge' | 'operations') — who
  grades the criterion; sub-criteria always inherit the parent's grader.
- `competition_rubric_criteria.sub_criteria` JSONB — optional one-level
  breakdown, e.g. Mission /15 -> clarity /5, implementation /5,
  creativity /5. `[]` = flat criterion, scored directly as before.
- `learner_teams.ops_criterion_scores / ops_criterion_notes /
  ops_scored_by / ops_scored_at` — the operations team's per-team scores,
  combined with the judge average on the leaderboard.

Revision ID: f6b3d94e1157
Revises: d7a1c92d0048
Create Date: 2026-09-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f6b3d94e1157'
down_revision = 'd7a1c92d0048'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'competition_rubric_criteria',
        sa.Column('scored_by', sa.String(length=32), nullable=False, server_default='judge'),
    )
    op.add_column(
        'competition_rubric_criteria',
        sa.Column('sub_criteria', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
    )
    op.add_column(
        'learner_teams',
        sa.Column('ops_criterion_scores', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
    )
    op.add_column('learner_teams', sa.Column('ops_criterion_notes', sa.Text(), nullable=True))
    op.add_column('learner_teams', sa.Column('ops_scored_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('learner_teams', sa.Column('ops_scored_at', sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        'fk_learner_teams_ops_scored_by_users', 'learner_teams', 'users',
        ['ops_scored_by'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_learner_teams_ops_scored_by_users', 'learner_teams', type_='foreignkey')
    op.drop_column('learner_teams', 'ops_scored_at')
    op.drop_column('learner_teams', 'ops_scored_by')
    op.drop_column('learner_teams', 'ops_criterion_notes')
    op.drop_column('learner_teams', 'ops_criterion_scores')
    op.drop_column('competition_rubric_criteria', 'sub_criteria')
    op.drop_column('competition_rubric_criteria', 'scored_by')
