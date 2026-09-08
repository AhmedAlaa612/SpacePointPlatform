"""Program-level role/openings template

Operator ask (2026-09): a new cohort should start with the same roles as
its program, without the program's later edits reaching back into cohorts
that already exist. `program_openings` is a one-time seed for
`cohort_openings` (copied by `create_cohort`, once) — a genuinely different
shape from how `cohort_openings` itself relates to `session_openings`
(live fallback, resolved at read time in `openings_for_session`). Same row
shape as `cohort_openings` because it exists to become one.

Revision ID: 4230948f677b
Revises: b3e1c07f45a2
Create Date: 2026-09-05 19:52:16.736058

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '4230948f677b'
down_revision: Union[str, None] = 'e21b9a4d7f18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "program_openings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("program_id", UUID(as_uuid=True), sa.ForeignKey("programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True), sa.ForeignKey("delivery_roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("slots", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("amount_aed", sa.Numeric(10, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("responsibilities_override", sa.Text(), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("program_id", "role_id", name="uq_program_opening_role"),
    )
    op.create_index("ix_program_openings_program_id", "program_openings", ["program_id"])


def downgrade() -> None:
    op.drop_index("ix_program_openings_program_id", table_name="program_openings")
    op.drop_table("program_openings")
