"""LMS program item: submission deadline + session fields (2026-08-31)

Adds an optional `deadline_at` to a `submission` item (enforced at submit
time, not a DB constraint) and 4 self-contained fields for a new `session`
item type (date, start time, location, meeting link) — never a live FK to
the Sessions domain's `Session` table, see `LmsProgramItem`'s own comment.

Revision ID: c8e1f9a4d2b6
Revises: a2c8e4f19b73
"""

import sqlalchemy as sa
from alembic import op

revision = "c8e1f9a4d2b6"
down_revision = "a2c8e4f19b73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("lms_program_items", sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("lms_program_items", sa.Column("session_date", sa.Date(), nullable=True))
    op.add_column("lms_program_items", sa.Column("session_starts_at", sa.Time(), nullable=True))
    op.add_column("lms_program_items", sa.Column("session_location", sa.String(length=255), nullable=True))
    op.add_column("lms_program_items", sa.Column("session_meeting_url", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("lms_program_items", "session_meeting_url")
    op.drop_column("lms_program_items", "session_location")
    op.drop_column("lms_program_items", "session_starts_at")
    op.drop_column("lms_program_items", "session_date")
    op.drop_column("lms_program_items", "deadline_at")
