"""design_component_library.updated_by (Design v2, 7D-7)

The library becomes editable from the app for the first time, and under D7
mission managers can edit it too — not just staff. Since the catalog is
global (no `mission_id`), an edit by one mission's manager is visible to
every design mission, so a bad change needs to be *attributable* rather
than silent.

Paired with the retire-not-delete rule enforced in the router: components
are never hard-deleted, only `is_active = false`. The RESTRICT foreign key
from `design_components` already made deletion impossible for anything ever
used; this makes the intent explicit rather than surfacing as a
foreign-key error.

Revision ID: f8c3d21b7e45
Revises: e7b2f14a9c60
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f8c3d21b7e45"
down_revision = "e7b2f14a9c60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "design_component_library",
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_design_component_library_updated_by", "design_component_library", "users",
        ["updated_by"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_design_component_library_updated_by", "design_component_library", type_="foreignkey")
    op.drop_column("design_component_library", "updated_by")
