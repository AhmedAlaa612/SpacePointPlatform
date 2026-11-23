"""Program landing pages (unified on website_events) & hybrid-live case studies.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a9b0
Create Date: 2026-11-22 17:10:00.000000
"""

from __future__ import annotations

import secrets
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a9b0"
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

    # 1. Organization 3-state program landing page publishing access
    if "organizations" in tables and "program_page_access" not in _column_names(bind, "organizations"):
        op.add_column(
            "organizations",
            sa.Column(
                "program_page_access",
                sa.String(length=20),
                nullable=False,
                server_default="disabled",
            ),
        )

    # 2. WebsiteEvent: link to Program + hybrid-live fields + private preview token
    if "website_events" in tables:
        ev_cols = _column_names(bind, "website_events")
        ev_idx = _index_names(bind, "website_events")
        if "program_id" not in ev_cols:
            op.add_column(
                "website_events",
                sa.Column(
                    "program_id",
                    postgresql.UUID(as_uuid=True),
                    sa.ForeignKey("programs.id", ondelete="CASCADE"),
                    nullable=True,
                ),
            )
        if "live_linked" not in ev_cols:
            op.add_column(
                "website_events",
                sa.Column("live_linked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if "overrides" not in ev_cols:
            op.add_column(
                "website_events",
                sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            )
        if "hidden_cohort_ids" not in ev_cols:
            op.add_column(
                "website_events",
                sa.Column("hidden_cohort_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            )
        if "hidden_sections" not in ev_cols:
            op.add_column(
                "website_events",
                sa.Column("hidden_sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            )
        if "preview_token" not in ev_cols:
            op.add_column(
                "website_events",
                sa.Column("preview_token", sa.String(length=64), nullable=True),
            )
        if "submitted_for_review_at" not in ev_cols:
            op.add_column(
                "website_events",
                sa.Column("submitted_for_review_at", sa.DateTime(timezone=True), nullable=True),
            )
        if "ix_website_events_program_id" not in ev_idx:
            op.create_index("ix_website_events_program_id", "website_events", ["program_id"])
        if "ix_website_events_preview_token" not in ev_idx:
            op.create_index("ix_website_events_preview_token", "website_events", ["preview_token"], unique=True)
        if "uq_website_events_program_id" not in ev_idx:
            op.create_index(
                "uq_website_events_program_id",
                "website_events",
                ["program_id"],
                unique=True,
                postgresql_where=sa.text("program_id IS NOT NULL"),
            )

    # 3. WebsiteCaseStudy: hybrid-live fields + private preview token
    if "website_case_studies" in tables:
        cs_cols = _column_names(bind, "website_case_studies")
        cs_idx = _index_names(bind, "website_case_studies")
        if "live_linked" not in cs_cols:
            op.add_column(
                "website_case_studies",
                sa.Column("live_linked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if "overrides" not in cs_cols:
            op.add_column(
                "website_case_studies",
                sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            )
        if "hidden_sections" not in cs_cols:
            op.add_column(
                "website_case_studies",
                sa.Column("hidden_sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            )
        if "preview_token" not in cs_cols:
            op.add_column(
                "website_case_studies",
                sa.Column("preview_token", sa.String(length=64), nullable=True),
            )
        if "ix_website_case_studies_preview_token" not in cs_idx:
            op.create_index("ix_website_case_studies_preview_token", "website_case_studies", ["preview_token"], unique=True)

    # 4. Backfill preview tokens on existing events & case studies
    if "website_events" in tables:
        ev_rows = bind.execute(sa.text("SELECT id FROM website_events WHERE preview_token IS NULL")).fetchall()
        for (ev_id,) in ev_rows:
            bind.execute(
                sa.text("UPDATE website_events SET preview_token = :tok WHERE id = :id"),
                {"tok": secrets.token_urlsafe(24), "id": ev_id},
            )

    if "website_case_studies" in tables:
        cs_rows = bind.execute(sa.text("SELECT id FROM website_case_studies WHERE preview_token IS NULL")).fetchall()
        for (cs_id,) in cs_rows:
            bind.execute(
                sa.text("UPDATE website_case_studies SET preview_token = :tok WHERE id = :id"),
                {"tok": secrets.token_urlsafe(24), "id": cs_id},
            )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)

    if "website_case_studies" in tables:
        cs_cols = _column_names(bind, "website_case_studies")
        cs_idx = _index_names(bind, "website_case_studies")
        if "ix_website_case_studies_preview_token" in cs_idx:
            op.drop_index("ix_website_case_studies_preview_token", table_name="website_case_studies")
        for col in ("preview_token", "hidden_sections", "overrides", "live_linked"):
            if col in cs_cols:
                op.drop_column("website_case_studies", col)

    if "website_events" in tables:
        ev_cols = _column_names(bind, "website_events")
        ev_idx = _index_names(bind, "website_events")
        for idx in ("uq_website_events_program_id", "ix_website_events_preview_token", "ix_website_events_program_id"):
            if idx in ev_idx:
                op.drop_index(idx, table_name="website_events")
        for col in (
            "submitted_for_review_at",
            "preview_token",
            "hidden_sections",
            "hidden_cohort_ids",
            "overrides",
            "live_linked",
            "program_id",
        ):
            if col in ev_cols:
                op.drop_column("website_events", col)

    if "organizations" in tables and "program_page_access" in _column_names(bind, "organizations"):
        op.drop_column("organizations", "program_page_access")
