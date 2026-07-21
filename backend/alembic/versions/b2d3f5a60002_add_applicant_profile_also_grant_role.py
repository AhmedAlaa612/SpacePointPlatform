"""add applicant_profiles.also_grant_role — extra role to grant on instructor
pipeline approval, for applicants routed in from another role's application

Revision ID: b2d3f5a60002
Revises: a1c9f2e40001
Create Date: 2026-07-21
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2d3f5a60002"
down_revision = "a1c9f2e40001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("applicant_profiles", sa.Column("also_grant_role", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("applicant_profiles", "also_grant_role")
