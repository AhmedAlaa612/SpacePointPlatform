"""add applicant_profiles.cv_path — CV upload on the instructor application

Revision ID: a1c9f2e40001
Revises: baseline
Create Date: 2026-07-17
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1c9f2e40001"
down_revision = "baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applicant_profiles", sa.Column("cv_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("applicant_profiles", "cv_path")
