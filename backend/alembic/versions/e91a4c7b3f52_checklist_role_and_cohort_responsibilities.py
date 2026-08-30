"""Per-role checklists, and a per-cohort responsibilities override

Operator ask, 2026-08-28: the daily checklist and the responsibilities text
an instructor agrees to are currently the same for every role on a session —
Lead and Assistant see the identical list either way. Two independent,
additive changes:

`delivery_checklist_items.role_id` — NULL means general (every role), a role
means that role's *own* list, which replaces the general one at whichever
level it's set rather than adding to it. Same override-not-merge shape the
program->cohort->session axis already uses, just crossed with role — see the
model docstring for the RESTRICT reasoning.

`cohort_openings.responsibilities_override` — `cohort_openings` is already
the one row per (cohort, role); a nullable text column there is the cohort
tier of the same override chain `get_responsibilities_for_role` already
walks (role.description -> general text), checked first.

Revision ID: e91a4c7b3f52
Revises: d4e81f3a06c5
Create Date: 2026-08-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "e91a4c7b3f52"
down_revision = "d4e81f3a06c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "delivery_checklist_items",
        sa.Column("role_id", UUID(as_uuid=True), sa.ForeignKey("delivery_roles.id", ondelete="RESTRICT"), nullable=True),
    )
    op.create_index("ix_delivery_checklist_items_role_id", "delivery_checklist_items", ["role_id"])

    op.add_column("cohort_openings", sa.Column("responsibilities_override", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("cohort_openings", "responsibilities_override")

    op.drop_index("ix_delivery_checklist_items_role_id", table_name="delivery_checklist_items")
    op.drop_column("delivery_checklist_items", "role_id")
