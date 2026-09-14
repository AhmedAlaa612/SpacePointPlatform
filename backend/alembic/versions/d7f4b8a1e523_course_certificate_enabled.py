"""course_certificate_enabled — courses.certificate_enabled (2026-09-14)

Per-course certificate opt-out. Defaults true so every existing course keeps
issuing completion certificates exactly as before; an admin can flip it off
for courses that shouldn't hand out a certificate (see
services/lms/certificates.py::issue_course_certificate, which is the only
read site).

Revision ID: d7f4b8a1e523
Revises: c9f4e1a68d75
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7f4b8a1e523'
down_revision: Union[str, None] = 'c9f4e1a68d75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'courses',
        sa.Column('certificate_enabled', sa.Boolean(), nullable=False, server_default='true'),
    )


def downgrade() -> None:
    op.drop_column('courses', 'certificate_enabled')
