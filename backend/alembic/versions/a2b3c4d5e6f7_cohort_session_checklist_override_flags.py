"""Add cohort and session checklist override flags.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-11-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()

    if "inherit_default_checklists" not in _column_names(bind, "cohorts"):
        op.add_column(
            "cohorts",
            sa.Column(
                "inherit_default_checklists",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
        )

    session_cols = _column_names(bind, "sessions")
    if "instructor_checklist_overridden" not in session_cols:
        op.add_column(
            "sessions",
            sa.Column(
                "instructor_checklist_overridden",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
    if "internal_checklist_overridden" not in session_cols:
        op.add_column(
            "sessions",
            sa.Column(
                "internal_checklist_overridden",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()

    session_cols = _column_names(bind, "sessions")
    if "internal_checklist_overridden" in session_cols:
        op.drop_column("sessions", "internal_checklist_overridden")
    if "instructor_checklist_overridden" in session_cols:
        op.drop_column("sessions", "instructor_checklist_overridden")

    if "inherit_default_checklists" in _column_names(bind, "cohorts"):
        op.drop_column("cohorts", "inherit_default_checklists")
