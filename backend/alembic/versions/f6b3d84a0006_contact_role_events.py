"""contact_role_events (V2 amendment: role-history timeline, operator request 2026-07-24)

Revision ID: f6b3d84a0006
Revises: e5a2c93f0005
Create Date: 2026-07-24
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "f6b3d84a0006"
down_revision = "e5a2c93f0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contact_role_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=8), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_contact_role_events_contact_occurred", "contact_role_events", ["contact_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_contact_role_events_contact_occurred", table_name="contact_role_events")
    op.drop_table("contact_role_events")
