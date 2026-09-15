"""invite_code_lms_program_grants — invite codes can grant a whole LMS
Program, not just courses/paths (2026-09-15)

Client ask: "can an invite code connect to an lms program directly?" — it
couldn't; `InvitationCodeGrant.product_type` only ever supported "course"
and "learning_path". Adds "lms_program" as a third product_type, backed by
a `cohort_id` column: an LmsProgram is never assigned standalone
(`assign_lms_program` always resolves it *from* a cohort, since a cohort's
own override can reshape the checklist), so the grant holds the cohort,
not an lms_program_id — see `models/lms/invite_grant.py`'s own docstring.

Revision ID: 256962fbd6e0
Revises: b726e963875f
Create Date: 2026-09-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '256962fbd6e0'
down_revision: Union[str, None] = 'b726e963875f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'invitation_code_grants',
        sa.Column('cohort_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_invitation_code_grants_cohort_id', 'invitation_code_grants', 'cohorts',
        ['cohort_id'], ['id'], ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('fk_invitation_code_grants_cohort_id', 'invitation_code_grants', type_='foreignkey')
    op.drop_column('invitation_code_grants', 'cohort_id')
