"""Targeted open calls: session_call_targets.

Operator decision (2026-07-26): "I wanted it really targeted, not just
notification wise." The instructor picker on the open-call dialog previously
only filtered who received the notification — the session still appeared on
every instructor's Available Sessions page and anyone could register interest.

Absence means unrestricted: a session with no rows here is open to every
instructor/facilitator, which is what every existing open call is. So this
migration adds the table and backfills nothing — all calls currently open stay
open to everyone, exactly as they behave today.

Revision ID: b3e8a41d0014
Revises: a1d7f36c0013
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b3e8a41d0014"
down_revision = "a1d7f36c0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_call_targets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "user_id", name="uq_session_call_target"),
    )
    op.create_index(
        "ix_session_call_targets_session_id", "session_call_targets", ["session_id"]
    )
    op.create_index(
        "ix_session_call_targets_user_id", "session_call_targets", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_session_call_targets_user_id", table_name="session_call_targets")
    op.drop_index("ix_session_call_targets_session_id", table_name="session_call_targets")
    op.drop_table("session_call_targets")
