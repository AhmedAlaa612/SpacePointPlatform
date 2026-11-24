"""LMS Interactive Books domain tables and extensions.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-11-24 12:40:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
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
    return {idx["name"] for idx in sa.inspect(bind).get_indexes(table) if idx.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)

    if "lms_books" not in tables:
        op.create_table(
            "lms_books",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("slug", sa.String(length=128), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("title_ar", sa.String(length=200), nullable=True),
            sa.Column("subtitle", sa.String(length=300), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("author_name", sa.String(length=160), nullable=True),
            sa.Column("cover_bucket", sa.String(length=64), nullable=True),
            sa.Column("cover_path", sa.String(length=512), nullable=True),
            sa.Column("languages", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[\"en\"]'::jsonb")),
            sa.Column("bundle_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("bundle_entry", sa.String(length=255), nullable=False, server_default="index.html"),
            sa.Column("bundle_storage_backend", sa.String(length=16), nullable=True),
            sa.Column("bundle_size_bytes", sa.Integer(), nullable=True),
            sa.Column("outline", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("profiles", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("default_profile", sa.String(length=32), nullable=False, server_default="all"),
            sa.Column("access_mode", sa.String(length=12), nullable=False, server_default="open"),
            sa.Column("access_days", sa.Integer(), nullable=True),
            sa.Column("price_cents", sa.Integer(), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="usd"),
            sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_lms_books_slug", "lms_books", ["slug"], unique=True)

    if "lms_book_enrollments" not in tables:
        op.create_table(
            "lms_book_enrollments",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("book_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_books.id", ondelete="CASCADE"), nullable=False),
            sa.Column("source", sa.String(length=16), nullable=False, server_default="self"),
            sa.Column("status", sa.String(length=10), nullable=False, server_default="active"),
            sa.Column("granted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("purchase_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("purchases.id", ondelete="SET NULL"), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "book_id", name="uq_lms_book_enrollments_user_book"),
        )
        op.create_index("ix_lms_book_enrollments_user_id", "lms_book_enrollments", ["user_id"])
        op.create_index("ix_lms_book_enrollments_book_id", "lms_book_enrollments", ["book_id"])
        op.create_index("ix_lms_book_enrollments_purchase_id", "lms_book_enrollments", ["purchase_id"])

    if "lms_book_progress" not in tables:
        op.create_table(
            "lms_book_progress",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("book_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_books.id", ondelete="CASCADE"), nullable=False),
            sa.Column("current_spread", sa.String(length=128), nullable=True),
            sa.Column("current_chapter", sa.String(length=64), nullable=True),
            sa.Column("active_profile", sa.String(length=32), nullable=True),
            sa.Column("visited_spreads", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("stars", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("stars_earned", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("stars_possible", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("completion_pct", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("raw_state", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "book_id", name="uq_lms_book_progress_user_book"),
        )
        op.create_index("ix_lms_book_progress_user_id", "lms_book_progress", ["user_id"])
        op.create_index("ix_lms_book_progress_book_id", "lms_book_progress", ["book_id"])

    if "lms_book_exercise_responses" not in tables:
        op.create_table(
            "lms_book_exercise_responses",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("book_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_books.id", ondelete="CASCADE"), nullable=False),
            sa.Column("chapter_key", sa.String(length=64), nullable=True),
            sa.Column("exercise_key", sa.String(length=160), nullable=False),
            sa.Column("exercise_type", sa.String(length=24), nullable=False),
            sa.Column("prompt_text", sa.Text(), nullable=True),
            sa.Column("answer_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("is_correct", sa.Boolean(), nullable=True),
            sa.Column("score_stars", sa.Integer(), nullable=True),
            sa.Column("max_stars", sa.Integer(), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("user_id", "book_id", "exercise_key", name="uq_lms_book_exercise_user_book_key"),
        )
        op.create_index("ix_lms_book_exercise_responses_user_id", "lms_book_exercise_responses", ["user_id"])
        op.create_index("ix_lms_book_exercise_responses_book_id", "lms_book_exercise_responses", ["book_id"])
        op.create_index("ix_lms_book_exercise_responses_chapter_key", "lms_book_exercise_responses", ["chapter_key"])

    if "purchases" in tables:
        p_cols = _column_names(bind, "purchases")
        p_idx = _index_names(bind, "purchases")
        if "book_id" not in p_cols:
            op.add_column(
                "purchases",
                sa.Column("book_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_books.id", ondelete="CASCADE"), nullable=True),
            )
        if "uq_purchases_pending_per_book" not in p_idx:
            op.create_index(
                "uq_purchases_pending_per_book",
                "purchases",
                ["user_id", "book_id"],
                unique=True,
                postgresql_where=sa.text("status = 'pending'"),
            )

    if "invitation_code_grants" in tables:
        g_cols = _column_names(bind, "invitation_code_grants")
        if "book_id" not in g_cols:
            op.add_column(
                "invitation_code_grants",
                sa.Column("book_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_books.id", ondelete="CASCADE"), nullable=True),
            )

    if "lms_program_items" in tables:
        pi_cols = _column_names(bind, "lms_program_items")
        if "book_id" not in pi_cols:
            op.add_column(
                "lms_program_items",
                sa.Column("book_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("lms_books.id", ondelete="RESTRICT"), nullable=True),
            )
        if "book_profile" not in pi_cols:
            op.add_column("lms_program_items", sa.Column("book_profile", sa.String(length=32), nullable=True))
        if "book_chapter" not in pi_cols:
            op.add_column("lms_program_items", sa.Column("book_chapter", sa.String(length=64), nullable=True))
        if "book_min_completion_pct" not in pi_cols:
            op.add_column("lms_program_items", sa.Column("book_min_completion_pct", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)

    if "lms_program_items" in tables:
        pi_cols = _column_names(bind, "lms_program_items")
        for col in ("book_min_completion_pct", "book_chapter", "book_profile", "book_id"):
            if col in pi_cols:
                op.drop_column("lms_program_items", col)

    if "invitation_code_grants" in tables and "book_id" in _column_names(bind, "invitation_code_grants"):
        op.drop_column("invitation_code_grants", "book_id")

    if "purchases" in tables:
        p_idx = _index_names(bind, "purchases")
        if "uq_purchases_pending_per_book" in p_idx:
            op.drop_index("uq_purchases_pending_per_book", table_name="purchases")
        if "book_id" in _column_names(bind, "purchases"):
            op.drop_column("purchases", "book_id")

    for tbl in ("lms_book_exercise_responses", "lms_book_progress", "lms_book_enrollments", "lms_books"):
        if tbl in tables:
            op.drop_table(tbl)
