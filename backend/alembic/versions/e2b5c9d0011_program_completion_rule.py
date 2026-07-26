"""W5 S5-3 follow-up (operator feedback): the 0.7 completion threshold was
hardcoded — move it onto Program so each admin can set it per program, as
either a percentage or an absolute session count. Defaults (percentage,
70) exactly match the previous hardcoded behavior, so every existing
program keeps working unchanged until an admin edits it.

Revision ID: e2b5c9d0011
Revises: d1a4f8c0010
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e2b5c9d0011"
down_revision = "d1a4f8c0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "programs",
        sa.Column("completion_rule_type", sa.String(length=16), nullable=False, server_default="percentage"),
    )
    op.add_column(
        "programs",
        sa.Column("completion_rule_value", sa.Numeric(6, 2), nullable=False, server_default="70"),
    )
    op.alter_column("programs", "completion_rule_type", server_default=None)
    op.alter_column("programs", "completion_rule_value", server_default=None)


def downgrade() -> None:
    op.drop_column("programs", "completion_rule_value")
    op.drop_column("programs", "completion_rule_type")
