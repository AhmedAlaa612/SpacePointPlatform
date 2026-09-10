"""Track onboarding-email send state on registrations and judge
assignments (2026-09-10) — additive nullable timestamp on each,
mirroring registrations.ticket_sent_at's existing shape. Lets the admin
UI show "onboarding sent" per student/judge and drive a manual
resend action, the same way ticket_sent_at already backs the ticket
badge/resend button.

Revision ID: a1c4e8f92d63
Revises: 06760f3b4ec0
Create Date: 2026-09-10 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c4e8f92d63'
down_revision: Union[str, None] = '06760f3b4ec0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('registrations', sa.Column('onboarding_sent_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('competition_judges', sa.Column('onboarding_sent_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('competition_judges', 'onboarding_sent_at')
    op.drop_column('registrations', 'onboarding_sent_at')
