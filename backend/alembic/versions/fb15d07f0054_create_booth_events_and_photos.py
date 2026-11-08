"""Create booth_events and booth_photos tables.

Revision ID: fb15d07f0054
Revises: fa14d06f0053
Create Date: 2026-11-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fb15d07f0054"
down_revision: Union[str, None] = "fa14d06f0053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "booth_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "invitation_code_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invitation_codes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("auto_create_lms_account", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("email_subject", sa.String(255), nullable=True),
        sa.Column("email_body_template", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_booth_events_slug", "booth_events", ["slug"], unique=True)
    op.create_index("ix_booth_events_invitation_code_id", "booth_events", ["invitation_code_id"])

    op.create_table(
        "booth_photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("booth_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("participant_name", sa.String(255), nullable=False),
        sa.Column("participant_email", sa.String(255), nullable=False),
        sa.Column("storage_bucket", sa.String(100), nullable=False, server_default="spacepoint-booth"),
        sa.Column("storage_path", sa.String(512), nullable=False),
        sa.Column("satellite_id", sa.String(100), nullable=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_new_lms_user", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("email_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_booth_photos_event_id", "booth_photos", ["event_id"])
    op.create_index("ix_booth_photos_participant_email", "booth_photos", ["participant_email"])
    op.create_index("ix_booth_photos_user_id", "booth_photos", ["user_id"])
    op.create_index("ix_booth_photos_created_at", "booth_photos", ["created_at"])


def downgrade() -> None:
    op.drop_table("booth_photos")
    op.drop_table("booth_events")
