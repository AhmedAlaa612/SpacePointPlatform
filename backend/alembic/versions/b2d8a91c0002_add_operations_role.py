"""add 'operations' to user_role enum — new ops role for registration/sessions/inventory (V2 R1-1)

Revision ID: b2d8a91c0002
Revises: b2d3f5a60002
Create Date: 2026-07-20
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2d8a91c0002"
down_revision = "b2d3f5a60002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'operations'")


def downgrade() -> None:
    # Postgres cannot drop a value from an enum type — no-op by design.
    pass
