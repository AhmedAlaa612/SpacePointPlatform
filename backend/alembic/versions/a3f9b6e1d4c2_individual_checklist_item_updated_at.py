"""Individual checklist items: track updated_at too (2026-08-27)

Student-facing checklist rows (submission-type items especially) need to
show "submitted [when]" the same way the team-scoped twin already does —
`lms_program_team_item_progress.updated_at` exists, but the individual
table never got the matching column, so every non-team submission's
timestamp was unavailable. Same column, same meaning; no updated_by_user_id
here since an individual row only ever has one possible author (the
assignment's own user), resolved from assignment_id instead.

Revision ID: a3f9b6e1d4c2
Revises: c0ecdcecc91c
"""

import sqlalchemy as sa
from alembic import op

revision = "a3f9b6e1d4c2"
down_revision = "c0ecdcecc91c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lms_program_item_progress",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lms_program_item_progress", "updated_at")
