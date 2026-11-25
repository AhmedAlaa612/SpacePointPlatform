"""Book custom editions, org book access grants, and cohort coordinator scoping.

Revision ID: a9b8c7d6e5f4
Revises: e6f7a8b9c0d1
Create Date: 2026-11-25 18:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, Sequence[str], None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _column_names(bind, table: str) -> set[str]:
    if table not in _table_names(bind):
        return set()
    return {col["name"] for col in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)

    if "lms_book_editions" not in tables:
        op.create_table(
            "lms_book_editions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("book_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_books.id", ondelete="CASCADE"), nullable=False),
            sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("title_ar", sa.String(length=200), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("chapter_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("default_lang", sa.String(length=8), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_lms_book_editions_book_id", "lms_book_editions", ["book_id"])
        op.create_index("ix_lms_book_editions_organization_id", "lms_book_editions", ["organization_id"])

    if "cohort_coordinators" not in tables:
        op.create_table(
            "cohort_coordinators",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("added_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("cohort_id", "user_id", name="uq_cohort_coordinators_cohort_user"),
        )
        op.create_index("ix_cohort_coordinators_cohort_id", "cohort_coordinators", ["cohort_id"])
        op.create_index("ix_cohort_coordinators_user_id", "cohort_coordinators", ["user_id"])

    org_cols = _column_names(bind, "organizations")
    if "book_scope" not in org_cols:
        op.add_column("organizations", sa.Column("book_scope", sa.String(length=20), nullable=False, server_default="none"))
    if "allowed_book_ids" not in org_cols:
        op.add_column(
            "organizations",
            sa.Column("allowed_book_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        )

    cohort_cols = _column_names(bind, "cohorts")
    if "coordinator_access_mode" not in cohort_cols:
        op.add_column(
            "cohorts",
            sa.Column("coordinator_access_mode", sa.String(length=16), nullable=False, server_default="general"),
        )

    enroll_cols = _column_names(bind, "lms_book_enrollments")
    if "book_edition_id" not in enroll_cols:
        op.add_column(
            "lms_book_enrollments",
            sa.Column("book_edition_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_book_editions.id", ondelete="SET NULL"), nullable=True),
        )

    item_cols = _column_names(bind, "lms_program_items")
    if "book_edition_id" not in item_cols:
        op.add_column(
            "lms_program_items",
            sa.Column("book_edition_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_book_editions.id", ondelete="SET NULL"), nullable=True),
        )
    if "book_chapters" not in item_cols:
        op.add_column(
            "lms_program_items",
            sa.Column("book_chapters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )

    grant_cols = _column_names(bind, "invitation_code_grants")
    if "book_edition_id" not in grant_cols:
        op.add_column(
            "invitation_code_grants",
            sa.Column("book_edition_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_book_editions.id", ondelete="SET NULL"), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)

    if "invitation_code_grants" in tables and "book_edition_id" in _column_names(bind, "invitation_code_grants"):
        op.drop_column("invitation_code_grants", "book_edition_id")
    if "lms_program_items" in tables:
        cols = _column_names(bind, "lms_program_items")
        if "book_chapters" in cols:
            op.drop_column("lms_program_items", "book_chapters")
        if "book_edition_id" in cols:
            op.drop_column("lms_program_items", "book_edition_id")
    if "lms_book_enrollments" in tables and "book_edition_id" in _column_names(bind, "lms_book_enrollments"):
        op.drop_column("lms_book_enrollments", "book_edition_id")
    if "cohorts" in tables and "coordinator_access_mode" in _column_names(bind, "cohorts"):
        op.drop_column("cohorts", "coordinator_access_mode")
    if "organizations" in tables:
        cols = _column_names(bind, "organizations")
        if "allowed_book_ids" in cols:
            op.drop_column("organizations", "allowed_book_ids")
        if "book_scope" in cols:
            op.drop_column("organizations", "book_scope")
    if "cohort_coordinators" in tables:
        op.drop_table("cohort_coordinators")
    if "lms_book_editions" in tables:
        op.drop_table("lms_book_editions")
