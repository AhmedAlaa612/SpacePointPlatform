"""Multiple concurrent calls per session

Operator ask (2026-08-01): "I should be able to open multiple targeted
calls, not only one, and view open calls public or targeted and edit them
or close them." Before this, `session_call_targets` was tagged only with
`session_id` — one flat target list per session, so a public call and a
targeted call could never run at the same time; opening a second call just
replaced the first's target list.

`session_calls` is the new "one campaign" row; `session_call_targets` gets
`call_id`, scoping each target row to the call that created it. Existing
data is backfilled rather than dropped:

- Every session that currently has target rows gets one `session_calls` row
  (status 'open' if the session is currently open_call, else 'closed'), and
  its target rows get tagged with that call's id.
- Every session that is currently open_call but has NO target rows (a plain
  public call) gets one `session_calls` row with status 'open' and no
  targets, so it shows up in the new "calls on this session" list instead of
  being invisible to it.

`session.staffing_status` is untouched — it stays the session-wide summary
(unstaffed|open_call|staffed), now meaning "at least one call is open"
rather than "the one call is open"; the service layer keeps it in sync.

Revision ID: c4e7a39f0028
Revises: b3d6f28e0027
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "c4e7a39f0028"
down_revision = "b3d6f28e0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_calls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("label", sa.String(64), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_session_calls_session_id", "session_calls", ["session_id"])

    op.add_column("session_call_targets", sa.Column("call_id", UUID(as_uuid=True), nullable=True))

    # One call per session that already has target rows, carrying that
    # session's current staffing_status as the call's own status.
    op.execute("""
        INSERT INTO session_calls (id, session_id, status, created_at)
        SELECT gen_random_uuid(), s.id,
               CASE WHEN s.staffing_status = 'open_call' THEN 'open' ELSE 'closed' END,
               now()
        FROM sessions s
        WHERE EXISTS (SELECT 1 FROM session_call_targets t WHERE t.session_id = s.id)
    """)
    op.execute("""
        UPDATE session_call_targets t
        SET call_id = c.id
        FROM session_calls c
        WHERE c.session_id = t.session_id
    """)

    # Sessions that are open_call with no existing target rows (a plain
    # public call) — give them a representable open call too.
    op.execute("""
        INSERT INTO session_calls (id, session_id, status, created_at)
        SELECT gen_random_uuid(), s.id, 'open', now()
        FROM sessions s
        WHERE s.staffing_status = 'open_call'
          AND NOT EXISTS (SELECT 1 FROM session_calls c WHERE c.session_id = s.id)
    """)

    op.alter_column("session_call_targets", "call_id", nullable=False)
    op.create_foreign_key(
        "fk_session_call_targets_call_id", "session_call_targets", "session_calls",
        ["call_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_session_call_targets_call_id", "session_call_targets", ["call_id"])
    op.drop_constraint("uq_session_call_target", "session_call_targets", type_="unique")
    op.create_unique_constraint("uq_session_call_target", "session_call_targets", ["call_id", "user_id"])


def downgrade() -> None:
    op.drop_constraint("uq_session_call_target", "session_call_targets", type_="unique")
    op.create_unique_constraint("uq_session_call_target", "session_call_targets", ["session_id", "user_id"])
    op.drop_index("ix_session_call_targets_call_id", table_name="session_call_targets")
    op.drop_constraint("fk_session_call_targets_call_id", "session_call_targets", type_="foreignkey")
    op.drop_column("session_call_targets", "call_id")
    op.drop_index("ix_session_calls_session_id", table_name="session_calls")
    op.drop_table("session_calls")
