"""Add organization readiness assessment scoping and org-owned presets/questions.

Revision ID: dd44ee55ff66
Revises: cc33dd44ee55
Create Date: 2026-11-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "dd44ee55ff66"
down_revision: Union[str, None] = "cc33dd44ee55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("readiness_scope", sa.String(length=32), nullable=False, server_default="own"),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "allowed_readiness_preset_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )

    for tbl in ("pre_session_quiz_questions", "pre_session_quiz_datasheets", "pre_session_quiz_presets"):
        op.add_column(
            tbl,
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_index(f"ix_{tbl}_organization_id", tbl, ["organization_id"], unique=False)
        op.create_foreign_key(
            f"fk_{tbl}_organization_id",
            tbl,
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    for tbl in ("pre_session_quiz_presets", "pre_session_quiz_datasheets", "pre_session_quiz_questions"):
        op.drop_constraint(f"fk_{tbl}_organization_id", tbl, type_="foreignkey")
        op.drop_index(f"ix_{tbl}_organization_id", table_name=tbl)
        op.drop_column(tbl, "organization_id")

    op.drop_column("organizations", "allowed_readiness_preset_ids")
    op.drop_column("organizations", "readiness_scope")
