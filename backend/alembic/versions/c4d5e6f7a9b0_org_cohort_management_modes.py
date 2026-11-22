"""add org cohort management modes and org-scoped locations and programs

Revision ID: c4d5e6f7a9b0
Revises: b3c4d5e6f7a8
Create Date: 2026-11-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4d5e6f7a9b0"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _column_names(bind, table: str) -> set[str]:
    if table not in _table_names(bind):
        return set()
    return {col["name"] for col in sa.inspect(bind).get_columns(table)}


def _index_names(bind, table: str) -> set[str]:
    if table not in _table_names(bind):
        return set()
    return {idx["name"] for idx in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if "cohorts" in _table_names(bind):
        cohort_cols = _column_names(bind, "cohorts")
        if "management_mode" not in cohort_cols:
            op.add_column(
                "cohorts",
                sa.Column(
                    "management_mode",
                    sa.String(length=20),
                    nullable=False,
                    server_default="spacepoint",
                ),
            )
            op.execute(
                sa.text(
                    """
                    UPDATE cohorts
                    SET management_mode = 'partner'
                    WHERE organization_id IS NOT NULL
                       OR EXISTS (
                           SELECT 1
                           FROM programs p
                           WHERE p.id = cohorts.program_id
                             AND p.organization_id IS NOT NULL
                       )
                    """
                )
            )
        if "ix_cohorts_management_mode" not in _index_names(bind, "cohorts"):
            op.create_index("ix_cohorts_management_mode", "cohorts", ["management_mode"])

    if "organizations" in _table_names(bind):
        org_cols = _column_names(bind, "organizations")
        if "program_scope" not in org_cols:
            op.add_column(
                "organizations",
                sa.Column(
                    "program_scope",
                    sa.String(length=20),
                    nullable=False,
                    server_default="own",
                ),
            )
        if "allowed_program_ids" not in org_cols:
            op.add_column(
                "organizations",
                sa.Column(
                    "allowed_program_ids",
                    postgresql.JSONB(astext_type=sa.Text()),
                    nullable=False,
                    server_default=sa.text("'[]'::jsonb"),
                ),
            )

    if "locations" in _table_names(bind):
        loc_cols = _column_names(bind, "locations")
        if "organization_id" not in loc_cols:
            op.add_column(
                "locations",
                sa.Column(
                    "organization_id",
                    postgresql.UUID(as_uuid=True),
                    sa.ForeignKey("organizations.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )
        if "ix_locations_organization_id" not in _index_names(bind, "locations"):
            op.create_index("ix_locations_organization_id", "locations", ["organization_id"])


def downgrade() -> None:
    bind = op.get_bind()

    if "locations" in _table_names(bind):
        if "ix_locations_organization_id" in _index_names(bind, "locations"):
            op.drop_index("ix_locations_organization_id", table_name="locations")
        if "organization_id" in _column_names(bind, "locations"):
            op.drop_column("locations", "organization_id")

    if "organizations" in _table_names(bind):
        org_cols = _column_names(bind, "organizations")
        if "allowed_program_ids" in org_cols:
            op.drop_column("organizations", "allowed_program_ids")
        if "program_scope" in org_cols:
            op.drop_column("organizations", "program_scope")

    if "cohorts" in _table_names(bind):
        if "ix_cohorts_management_mode" in _index_names(bind, "cohorts"):
            op.drop_index("ix_cohorts_management_mode", table_name="cohorts")
        if "management_mode" in _column_names(bind, "cohorts"):
            op.drop_column("cohorts", "management_mode")
