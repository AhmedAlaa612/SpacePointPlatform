"""Bring single-session interest up to parity with cohort-call interest

Operator ask (2026-08-30): a standalone session's "register interest" form
was missing the operations process doc §2 support questions (transport,
travelling from another city, ops support, free-text concerns) that a
cohort call's form already asks — `instructor_interests` never got these
columns when `cohort_call_interests` was built for them on 2026-08-24.
Mirrors that table's same-named columns exactly.

Revision ID: b3f8c6a91d47
Revises: e91a4c7b3f52
Create Date: 2026-08-30
"""

import sqlalchemy as sa
from alembic import op

revision = "b3f8c6a91d47"
down_revision = "e91a4c7b3f52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instructor_interests",
        sa.Column("needs_transport", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "instructor_interests",
        sa.Column("needs_ops_support", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "instructor_interests",
        sa.Column("travelling_from_other_city", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("instructor_interests", sa.Column("concerns", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("instructor_interests", "concerns")
    op.drop_column("instructor_interests", "travelling_from_other_city")
    op.drop_column("instructor_interests", "needs_ops_support")
    op.drop_column("instructor_interests", "needs_transport")
