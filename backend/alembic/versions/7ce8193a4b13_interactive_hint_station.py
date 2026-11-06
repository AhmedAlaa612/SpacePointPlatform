"""interactive_hint_station

Revision ID: 7ce8193a4b13
Revises: 7ce8193a4b12
Create Date: 2026-11-05 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7ce8193a4b13'
down_revision: Union[str, None] = '7ce8193a4b12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cohort_hint_challenges',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('owner_type', sa.String(length=32), nullable=False),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('challenge_code', sa.String(length=64), nullable=True),
        sa.Column('topic', sa.String(length=128), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('mission_statement', sa.Text(), nullable=True),
        sa.Column('max_points', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_cohort_hint_challenges_owner_type', 'cohort_hint_challenges', ['owner_type'])
    op.create_index('ix_cohort_hint_challenges_owner_id', 'cohort_hint_challenges', ['owner_id'])
    op.create_unique_constraint('uq_hint_challenges_owner_pos', 'cohort_hint_challenges', ['owner_type', 'owner_id', 'position'])

    op.create_table(
        'cohort_hint_cards',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('challenge_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cohort_hint_challenges.id', ondelete='CASCADE'), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('level_label', sa.String(length=64), nullable=False),
        sa.Column('badge_label', sa.String(length=64), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('teaser', sa.Text(), nullable=True),
        sa.Column('revealed_content', sa.Text(), nullable=False),
        sa.Column('point_deduction', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('unlock_order', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_cohort_hint_cards_challenge_id', 'cohort_hint_cards', ['challenge_id'])
    op.create_unique_constraint('uq_hint_cards_challenge_order', 'cohort_hint_cards', ['challenge_id', 'unlock_order'])

    op.create_table(
        'cohort_team_hint_reveals',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cohort_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cohorts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('learner_teams.id', ondelete='CASCADE'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True),
        sa.Column('challenge_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cohort_hint_challenges.id', ondelete='CASCADE'), nullable=False),
        sa.Column('hint_card_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cohort_hint_cards.id', ondelete='CASCADE'), nullable=False),
        sa.Column('revealed_by_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('points_deducted', sa.Integer(), nullable=False),
        sa.Column('revealed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_cohort_team_hint_reveals_cohort_id', 'cohort_team_hint_reveals', ['cohort_id'])
    op.create_index('ix_cohort_team_hint_reveals_team_id', 'cohort_team_hint_reveals', ['team_id'])
    op.create_index('ix_cohort_team_hint_reveals_user_id', 'cohort_team_hint_reveals', ['user_id'])
    op.create_index('ix_cohort_team_hint_reveals_challenge_id', 'cohort_team_hint_reveals', ['challenge_id'])
    op.create_index('ix_cohort_team_hint_reveals_hint_card_id', 'cohort_team_hint_reveals', ['hint_card_id'])

    # Backstop against a concurrent double-reveal (two teammates clicking at
    # the same moment both pass the "already revealed?" check before either
    # inserts, then double-deduct). Partial indexes: one row per card per
    # team, and one per card per individual user (workshop, no-team mode).
    op.create_index(
        'uq_hint_reveals_team_card', 'cohort_team_hint_reveals',
        ['cohort_id', 'hint_card_id', 'team_id'], unique=True,
        postgresql_where=sa.text('team_id IS NOT NULL'),
    )
    op.create_index(
        'uq_hint_reveals_user_card', 'cohort_team_hint_reveals',
        ['cohort_id', 'hint_card_id', 'user_id'], unique=True,
        postgresql_where=sa.text('user_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_hint_reveals_user_card', table_name='cohort_team_hint_reveals')
    op.drop_index('uq_hint_reveals_team_card', table_name='cohort_team_hint_reveals')
    op.drop_table('cohort_team_hint_reveals')
    op.drop_table('cohort_hint_cards')
    op.drop_table('cohort_hint_challenges')
