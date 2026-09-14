"""team_mission_run_shared_attempt — lms_program_team_item_progress.mission_attempt_id
(2026-09) — a team-scoped mission_run item's shared MissionAttempt now
lives on the team's own progress row (one source of truth per team),
instead of being duplicated onto every teammate's individual
LmsProgramItemProgress row. See that column's own docstring for why.

Revision ID: d3e8f6c1a927
Revises: c9f4e1a68d75
Create Date: 2026-09-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'd3e8f6c1a927'
down_revision: Union[str, None] = 'c9f4e1a68d75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'lms_program_team_item_progress',
        sa.Column('mission_attempt_id', UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_lms_program_team_item_progress_mission_attempt_id', 'lms_program_team_item_progress',
        'mission_attempts', ['mission_attempt_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint(
        'fk_lms_program_team_item_progress_mission_attempt_id', 'lms_program_team_item_progress',
        type_='foreignkey',
    )
    op.drop_column('lms_program_team_item_progress', 'mission_attempt_id')
