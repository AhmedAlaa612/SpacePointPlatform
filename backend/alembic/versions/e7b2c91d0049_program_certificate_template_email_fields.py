"""add email_subject and email_body to program_certificate_templates

Revision ID: e7b2c91d0049
Revises: 1f9b1c3f39a4
Create Date: 2026-09-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'e7b2c91d0049'
down_revision: Union[str, None] = '1f9b1c3f39a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE cohorts ADD COLUMN IF NOT EXISTS submission_windows JSONB NOT NULL DEFAULT '[]'")
    op.execute("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS first_locked_at TIMESTAMP WITH TIME ZONE")
    op.execute("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS timing_adjustment_override DOUBLE PRECISION")
    op.execute("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS timing_adjustment_notes VARCHAR(255)")
    op.execute("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS qualification VARCHAR(50)")
    op.add_column('program_certificate_templates', sa.Column('email_subject', sa.String(255), nullable=True))
    op.add_column('program_certificate_templates', sa.Column('email_body', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('program_certificate_templates', 'email_body')
    op.drop_column('program_certificate_templates', 'email_subject')
    op.execute("ALTER TABLE learner_teams DROP COLUMN IF EXISTS qualification")
    op.execute("ALTER TABLE learner_teams DROP COLUMN IF EXISTS timing_adjustment_notes")
    op.execute("ALTER TABLE learner_teams DROP COLUMN IF EXISTS timing_adjustment_override")
    op.execute("ALTER TABLE learner_teams DROP COLUMN IF EXISTS first_locked_at")
    op.execute("ALTER TABLE cohorts DROP COLUMN IF EXISTS submission_windows")
