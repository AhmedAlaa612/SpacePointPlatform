"""applicant_profiles.pending_intern_details

Revision ID: 8b3f21a0e6c1
Revises: 52fd87c0a2e4
Create Date: 2026-08-20

Backs Path 2 of the internship-letter flow (HANDOFF_INTERNSHIP.md): the
internship-letter fields admin fills in when sending an intern application to
instructor onboarding, replayed automatically by review_applicant() once that
pipeline is approved.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '8b3f21a0e6c1'
down_revision: Union[str, None] = '52fd87c0a2e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('applicant_profiles', sa.Column('pending_intern_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('applicant_profiles', 'pending_intern_details')
