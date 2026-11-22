"""Program landing pages (unified on website_events) & hybrid-live case studies.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a9b0
Create Date: 2026-11-22 17:10:00.000000
"""

from __future__ import annotations

import re
import secrets
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _slugify(val: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (val or "").strip().lower()).strip("-")
    return s or "program"


def upgrade() -> None:
    # 1. Organization 3-state program landing page publishing access
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
    op.add_column(
        "website_events",
        sa.Column(
            "program_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("programs.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "website_events",
        sa.Column("live_linked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "website_events",
        sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "website_events",
        sa.Column("hidden_cohort_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "website_events",
        sa.Column("hidden_sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "website_events",
        sa.Column("preview_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "website_events",
        sa.Column("submitted_for_review_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_website_events_program_id", "website_events", ["program_id"])
    op.create_index("ix_website_events_preview_token", "website_events", ["preview_token"], unique=True)
    op.create_index(
        "uq_website_events_program_id",
        "website_events",
        ["program_id"],
        unique=True,
        postgresql_where=sa.text("program_id IS NOT NULL"),
    )

    # 3. WebsiteCaseStudy: hybrid-live fields + private preview token
    op.add_column(
        "website_case_studies",
        sa.Column("live_linked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "website_case_studies",
        sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "website_case_studies",
        sa.Column("hidden_sections", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "website_case_studies",
        sa.Column("preview_token", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_website_case_studies_preview_token", "website_case_studies", ["preview_token"], unique=True)

    # 4. Backfill preview tokens on existing events & case studies
    conn = op.get_bind()
    ev_rows = conn.execute(sa.text("SELECT id FROM website_events WHERE preview_token IS NULL")).fetchall()
    for (ev_id,) in ev_rows:
        conn.execute(
            sa.text("UPDATE website_events SET preview_token = :tok WHERE id = :id"),
            {"tok": secrets.token_urlsafe(24), "id": ev_id},
        )

    cs_rows = conn.execute(sa.text("SELECT id FROM website_case_studies WHERE preview_token IS NULL")).fetchall()
    for (cs_id,) in cs_rows:
        conn.execute(
            sa.text("UPDATE website_case_studies SET preview_token = :tok WHERE id = :id"),
            {"tok": secrets.token_urlsafe(24), "id": cs_id},
        )


def downgrade() -> None:
    op.drop_index("ix_website_case_studies_preview_token", table_name="website_case_studies")
    op.drop_column("website_case_studies", "preview_token")
    op.drop_column("website_case_studies", "hidden_sections")
    op.drop_column("website_case_studies", "overrides")
    op.drop_column("website_case_studies", "live_linked")

    op.drop_index("uq_website_events_program_id", table_name="website_events")
    op.drop_index("ix_website_events_preview_token", table_name="website_events")
    op.drop_index("ix_website_events_program_id", table_name="website_events")
    op.drop_column("website_events", "submitted_for_review_at")
    op.drop_column("website_events", "preview_token")
    op.drop_column("website_events", "hidden_sections")
    op.drop_column("website_events", "hidden_cohort_ids")
    op.drop_column("website_events", "overrides")
    op.drop_column("website_events", "live_linked")
    op.drop_column("website_events", "program_id")

    op.drop_column("organizations", "program_page_access")
