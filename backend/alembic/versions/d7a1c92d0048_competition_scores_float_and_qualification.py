"""competition scores float, timing adjustment, comments, and qualification

Revision ID: d7a1c92d0048
Revises: f5a1c92d0047
Create Date: 2026-09-22 22:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd7a1c92d0048'
down_revision = 'f5a1c92d0047'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Alter total_points and bonus_points to DOUBLE PRECISION (Float)
    op.alter_column(
        'competition_scores',
        'total_points',
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using='total_points::double precision'
    )
    op.alter_column(
        'competition_scores',
        'bonus_points',
        existing_type=sa.Integer(),
        type_=sa.Float(),
        existing_nullable=False,
        postgresql_using='bonus_points::double precision'
    )

    # 2. Add timing_adjustment, criterion_comments, notes to competition_scores
    op.add_column(
        'competition_scores',
        sa.Column('timing_adjustment', sa.Float(), nullable=False, server_default='0')
    )
    op.add_column(
        'competition_scores',
        sa.Column('criterion_comments', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}')
    )
    op.add_column(
        'competition_scores',
        sa.Column('notes', sa.Text(), nullable=True)
    )

    # 3. Add qualification to learner_teams
    op.add_column(
        'learner_teams',
        sa.Column('qualification', sa.String(length=50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('learner_teams', 'qualification')
    op.drop_column('competition_scores', 'notes')
    op.drop_column('competition_scores', 'criterion_comments')
    op.drop_column('competition_scores', 'timing_adjustment')
    op.alter_column(
        'competition_scores',
        'bonus_points',
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using='round(bonus_points)::integer'
    )
    op.alter_column(
        'competition_scores',
        'total_points',
        existing_type=sa.Float(),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using='round(total_points)::integer'
    )
