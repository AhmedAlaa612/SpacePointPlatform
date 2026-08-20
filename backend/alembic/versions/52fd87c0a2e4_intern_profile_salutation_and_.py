"""intern_profiles: salutation, supervisor_title, letter_date

Revision ID: 52fd87c0a2e4
Revises: 97af2eb4adcb
Create Date: 2026-08-20

No gender/title field exists anywhere in the schema. Admin types both at
approval time (routers/internship.py); stored here (not just used
transiently) so re-rendering the letter at sign time reproduces identical
text instead of going blank. `letter_date` freezes the printed `Date:`
field at first-generation time, same "instructor_since" convention as
InstructorProfile/contract.py — otherwise it would drift to today() on
every re-render (e.g. signing). Autogenerate also reported a long list of
unrelated baseline drift (index naming, TEXT->String type noise) on other
tables — the known pre-existing drift this repo already carries; not
included here, only the three intentional columns.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '52fd87c0a2e4'
down_revision: Union[str, None] = '97af2eb4adcb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('intern_profiles', sa.Column('salutation', sa.String(length=20), nullable=True))
    op.add_column('intern_profiles', sa.Column('supervisor_title', sa.String(length=20), nullable=True))
    op.add_column('intern_profiles', sa.Column('letter_date', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('intern_profiles', 'letter_date')
    op.drop_column('intern_profiles', 'supervisor_title')
    op.drop_column('intern_profiles', 'salutation')
