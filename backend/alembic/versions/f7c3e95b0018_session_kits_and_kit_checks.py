"""session_kits + kit_checks — the session loop (I2-1/I2-2)

`session_kits` is the *plan*: which kits ops earmarked for a session.
`movements` remains what actually happened. Keeping them apart is what lets a
pre-session check say "you were supposed to have five and you confirmed four".

`kit_checks.missing` is a snapshot rather than something recomputed on read: a
template's bill of materials changes over time, but what was missing on the day
does not, and recomputing an old check against today's BOM would quietly
rewrite history.

`kit_checks.skipped` makes "chose to start without counting" distinguishable
from "hasn't got to it yet". The pre-session check is a soft gate — an
instructor standing in front of thirty students has to be able to start — so
skipping must be *recordable*, not merely possible. Without it a post-session
shortage has no baseline and nobody can tell whether the kit arrived that way.

Revision ID: f7c3e95b0018
Revises: e6b2d84a0017
Create Date: 2026-07-29
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f7c3e95b0018"
down_revision = "e6b2d84a0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_kits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "kit_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kits.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "kit_id", name="uq_session_kit"),
    )
    op.create_index("ix_session_kits_session_id", "session_kits", ["session_id"])
    op.create_index("ix_session_kits_kit_id", "session_kits", ["kit_id"])

    op.create_table(
        "kit_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "kit_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kits.id", ondelete="CASCADE"), nullable=False,
        ),
        # SET NULL, not CASCADE: deleting a session must not erase the record
        # that somebody counted this kit and found things missing.
        sa.Column(
            "session_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("phase", sa.String(8), nullable=False),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "checked_by", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("counts", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("missing", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_kit_checks_kit_id", "kit_checks", ["kit_id"])
    op.create_index("ix_kit_checks_session_id", "kit_checks", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_kit_checks_session_id", table_name="kit_checks")
    op.drop_index("ix_kit_checks_kit_id", table_name="kit_checks")
    op.drop_table("kit_checks")
    op.drop_index("ix_session_kits_kit_id", table_name="session_kits")
    op.drop_index("ix_session_kits_session_id", table_name="session_kits")
    op.drop_table("session_kits")
