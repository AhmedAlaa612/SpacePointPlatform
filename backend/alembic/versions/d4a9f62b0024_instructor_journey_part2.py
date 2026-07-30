"""The rest of the instructor journey (I5-5 … I5-8)

Five additive changes, one revision, because they are one story — invite →
accept → materials → deliver → pay → certificate — and splitting them would
mean five migrations nobody reviews separately.

**`session_materials`** (I5-6). Operator decision: a program has materials, a
cohort can override them, and they can also be assigned to a single session —
the same three-level shape `price` and `duration_hours` use. Exactly one owner
column is set (CHECK), and a row is either a stored file or a link, never both
(CHECK). Unlike a scalar, "override" means *the nearest level with any rows
wins outright* — merging would make it impossible to drop a program-level file
for one cohort.

**`cohorts.location_map_url`** (I5-5). Instructors were sent an address and
left to find it.

**`instructor_interests.responsibilities_accepted_at` / `_version`** (I5-5).
Read-and-agree on the invite. The text is versioned in `portal_settings`; the
*version* is stored alongside the timestamp so editing the text later cannot
retroactively change what somebody agreed to.

**`payment_letters.issue_certificates`** (I5-7). Certificates already generate
on signing; this makes that optional. Defaults true — existing behaviour
unchanged.

**`payment_sessions.session_id`** (I5-8). Nullable FK, so hand-typed lines keep
working. It is what prevents a completed session being billed twice, and
SET NULL rather than CASCADE because deleting a session must not erase a
payment record.

Revision ID: d4a9f62b0024
Revises: c3d8e51a0023
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "d4a9f62b0024"
down_revision = "c3d8e51a0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_materials",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id", UUID(as_uuid=True),
                  sa.ForeignKey("programs.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("cohort_id", UUID(as_uuid=True),
                  sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("session_id", UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("bucket", sa.String(64), nullable=True),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("uploaded_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "(CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_material_exactly_one_owner",
        ),
        sa.CheckConstraint(
            "(file_path IS NOT NULL) <> (url IS NOT NULL)",
            name="ck_material_file_xor_link",
        ),
    )

    op.add_column("cohorts", sa.Column("location_map_url", sa.Text(), nullable=True))

    op.add_column(
        "instructor_interests",
        sa.Column("responsibilities_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "instructor_interests", sa.Column("responsibilities_version", sa.String(32), nullable=True)
    )

    op.add_column(
        "payment_letters",
        sa.Column("issue_certificates", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.add_column(
        "payment_sessions",
        sa.Column("session_id", UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_payment_sessions_session_id", "payment_sessions", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_sessions_session_id", table_name="payment_sessions")
    op.drop_column("payment_sessions", "session_id")
    op.drop_column("payment_letters", "issue_certificates")
    op.drop_column("instructor_interests", "responsibilities_version")
    op.drop_column("instructor_interests", "responsibilities_accepted_at")
    op.drop_column("cohorts", "location_map_url")
    op.drop_table("session_materials")
