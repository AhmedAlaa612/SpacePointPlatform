"""user_invitation_codes join table for multi-code student redemption.

Revision ID: f7a8b9c0d1e2
Revises: ff12bc34de61
Create Date: 2026-10-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "ff12bc34de61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_invitation_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invitation_code_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invitation_codes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column(
            "redeemed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "user_id", "invitation_code_id", name="uq_user_invitation_codes_user_code"
        ),
    )
    op.create_index(
        "ix_user_invitation_codes_user_id", "user_invitation_codes", ["user_id"]
    )
    op.create_index(
        "ix_user_invitation_codes_invitation_code_id",
        "user_invitation_codes",
        ["invitation_code_id"],
    )
    op.create_index(
        "ix_user_invitation_codes_code", "user_invitation_codes", ["code"]
    )

    # Backfill existing single-code records from users.invitation_code_used
    op.execute(
        """
        INSERT INTO user_invitation_codes (id, user_id, invitation_code_id, code, redeemed_at)
        SELECT
            gen_random_uuid(),
            u.id,
            ic.id,
            ic.code,
            COALESCE(u.created_at, now())
        FROM users u
        JOIN invitation_codes ic ON UPPER(TRIM(u.invitation_code_used)) = ic.code
        WHERE u.invitation_code_used IS NOT NULL
        ON CONFLICT (user_id, invitation_code_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_user_invitation_codes_code", table_name="user_invitation_codes")
    op.drop_index(
        "ix_user_invitation_codes_invitation_code_id",
        table_name="user_invitation_codes",
    )
    op.drop_index("ix_user_invitation_codes_user_id", table_name="user_invitation_codes")
    op.drop_table("user_invitation_codes")
