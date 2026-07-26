"""add users.contact_id FK -> contacts.id (V2 R2-6: staff become contacts too)

Revision ID: c3e0a71d0003
Revises: 8181f89a51df
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "c3e0a71d0003"
down_revision = "8181f89a51df"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_users_contact_id", "users", "contacts", ["contact_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_users_contact_id", "users", ["contact_id"])


def downgrade() -> None:
    op.drop_index("ix_users_contact_id", table_name="users")
    op.drop_constraint("fk_users_contact_id", "users", type_="foreignkey")
    op.drop_column("users", "contact_id")
