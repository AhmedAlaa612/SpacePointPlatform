"""add 'lms_author' to user_role enum and create lms_author_profiles table

Revision ID: 81a9c3d4e5f6
Revises: 708204e63b20
Create Date: 2026-10-02 18:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '81a9c3d4e5f6'
down_revision = '708204e63b20'
branch_labels = None
depends_on = None


def upgrade():
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in Postgres.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'lms_author'")

    op.create_table(
        "lms_author_profiles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("can_publish", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("scope_all", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "invitation_codes",
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )


def downgrade():
    op.drop_column("invitation_codes", "created_by")
    op.drop_table("lms_author_profiles")
    # Note: Enum values in PostgreSQL cannot be removed easily without recreating the type.
