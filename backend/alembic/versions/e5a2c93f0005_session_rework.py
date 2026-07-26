"""Session rework (V2 amendment, 2026-07-23): SessionMeeting -> Session
(title/material_url/price), per-session instructor assignment replacing
cohort-level, registration-to-session coverage, contacts.full_name single
field (no age/minor tracking, no separate Arabic name), program_type
'session' -> 'info_session'.

Revision ID: e5a2c93f0005
Revises: d4f1b82e0004
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e5a2c93f0005"
down_revision = "d4f1b82e0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── session_meetings -> sessions: real unit, not just a date ────────────
    op.rename_table("session_meetings", "sessions")
    op.alter_column("sessions", "topic", new_column_name="title")
    op.add_column("sessions", sa.Column("material_url", sa.Text(), nullable=True))
    op.add_column("sessions", sa.Column("price", sa.Numeric(10, 2), nullable=True))
    op.execute("ALTER TABLE sessions RENAME CONSTRAINT uq_session_meeting_slot TO uq_session_slot")

    # ── attendance_records: session_meeting_id -> session_id ────────────────
    op.alter_column("attendance_records", "session_meeting_id", new_column_name="session_id")
    op.execute(
        "ALTER TABLE attendance_records "
        "RENAME CONSTRAINT uq_attendance_registration_meeting TO uq_attendance_registration_session"
    )

    # ── session_reports: session_meeting_id -> session_id ───────────────────
    op.alter_column("session_reports", "session_meeting_id", new_column_name="session_id")

    # ── cohort_instructors (unused, staffing marketplace not built yet)
    #    replaced by session_instructors: instructors are assigned per
    #    session, not blanket-assigned to a whole cohort. ─────────────────────
    op.drop_table("cohort_instructors")

    op.create_table(
        "session_instructors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="lead"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("session_id", "user_id", name="uq_session_instructor"),
    )

    # ── registration_sessions: which session(s) a registration covers ───────
    # No rows for a registration = covers every session in the cohort.
    op.create_table(
        "registration_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("registration_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("registrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("registration_id", "session_id", name="uq_registration_session"),
    )

    # ── contacts: one plain name field, no age/minor tracking ───────────────
    op.alter_column("contacts", "full_name_latin", new_column_name="full_name")
    op.drop_column("contacts", "full_name_arabic")
    op.drop_column("contacts", "date_of_birth")
    op.drop_column("contacts", "is_minor")

    # ── programs: avoid "Session" meaning two different things ─────────────
    op.execute("UPDATE programs SET program_type = 'info_session' WHERE program_type = 'session'")


def downgrade() -> None:
    op.execute("UPDATE programs SET program_type = 'session' WHERE program_type = 'info_session'")

    op.add_column("contacts", sa.Column("is_minor", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("contacts", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column("contacts", sa.Column("full_name_arabic", sa.String(255), nullable=True))
    op.alter_column("contacts", "full_name", new_column_name="full_name_latin")

    op.drop_table("registration_sessions")
    op.drop_table("session_instructors")

    op.create_table(
        "cohort_instructors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("cohort_id", "user_id", name="uq_cohort_instructor"),
    )

    op.alter_column("session_reports", "session_id", new_column_name="session_meeting_id")

    op.execute(
        "ALTER TABLE attendance_records "
        "RENAME CONSTRAINT uq_attendance_registration_session TO uq_attendance_registration_meeting"
    )
    op.alter_column("attendance_records", "session_id", new_column_name="session_meeting_id")

    op.execute("ALTER TABLE sessions RENAME CONSTRAINT uq_session_slot TO uq_session_meeting_slot")
    op.drop_column("sessions", "price")
    op.drop_column("sessions", "material_url")
    op.alter_column("sessions", "title", new_column_name="topic")
    op.rename_table("sessions", "session_meetings")
