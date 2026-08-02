"""session_kits receipt/return tracking — replaces kit custody

There is no custody leg for kits any more: ops doesn't "hand out" a kit and
an instructor doesn't "hand it back". `session_kits` gains the whole story
instead — the instructor confirms they have the kit (`received_at`), and
later reports it back or says it's coming later (`return_status` /
`returned_at`). Ops reviews that report (`ops_confirmed_at`) in the session
review screen; actually moving the kit onto a shelf is a separate, ordinary
inventory move, not something this table triggers.

A companion change removes the old issue/collected/return movement legs and
the auto-issue-on-assignment behaviour from the application code — this
migration only adds the columns those new endpoints need.

Revision ID: e3f8b04c0030
Revises: d2e6f81a0029
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "e3f8b04c0030"
down_revision = "d2e6f81a0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("session_kits", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "session_kits",
        sa.Column(
            "received_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
    )

    op.add_column("session_kits", sa.Column("return_status", sa.String(16), nullable=True))
    op.add_column("session_kits", sa.Column("returned_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "session_kits",
        sa.Column(
            "returned_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.add_column("session_kits", sa.Column("return_note", sa.Text(), nullable=True))

    op.add_column("session_kits", sa.Column("ops_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "session_kits",
        sa.Column(
            "ops_confirmed_by", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("session_kits", "ops_confirmed_by")
    op.drop_column("session_kits", "ops_confirmed_at")
    op.drop_column("session_kits", "return_note")
    op.drop_column("session_kits", "returned_by")
    op.drop_column("session_kits", "returned_at")
    op.drop_column("session_kits", "return_status")
    op.drop_column("session_kits", "received_by")
    op.drop_column("session_kits", "received_at")
