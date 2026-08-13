"""Split invitation codes into student/instructor pools + Madar's batch label (2026-08-13)

`invitation_codes` was a single pool serving both `/auth/instructor-apply`
and LMS student signup, so one code unlocked both. With the code becoming a
required gate for student signup (operator, 2026-08-13) that's wrong: a code
issued for a school batch would also let someone apply as an instructor.

`kind` splits the pool. Every existing row backfills to 'instructor' — that
is what they were all issued for; the student side had no codes of its own
because the field was optional and unmanaged.

`label` is Madar's batch identity ("Fall 2026 Batch", MISSIONS_REPORT.md
§155, where invitation_codes doubled as cohort identity). It's what makes
the students-management filter readable — nobody wants to filter a roster by
"SP-8F2A".

Revision ID: c15604b9448b
Revises: 2608ca6f7434
Create Date: 2026-08-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c15604b9448b"
down_revision: Union[str, None] = "2608ca6f7434"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invitation_codes",
        sa.Column("kind", sa.String(16), nullable=False, server_default="instructor"),
    )
    op.add_column("invitation_codes", sa.Column("label", sa.String(120), nullable=True))
    op.create_index("ix_invitation_codes_kind", "invitation_codes", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_invitation_codes_kind", table_name="invitation_codes")
    op.drop_column("invitation_codes", "label")
    op.drop_column("invitation_codes", "kind")
