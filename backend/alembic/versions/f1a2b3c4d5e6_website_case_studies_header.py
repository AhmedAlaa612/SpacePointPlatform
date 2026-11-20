"""Create website_case_studies_header table and seed default stats & partners.

Revision ID: f1a2b3c4d5e6
Revises: ee55ff66aa77
Create Date: 2026-11-20
"""

import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.services.website_case_studies import (
    DEFAULT_CASE_STUDIES_HEADER_PARTNERS,
    DEFAULT_CASE_STUDIES_HEADER_STATS,
)

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "ee55ff66aa77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("website_case_studies_header"):
        op.create_table(
            "website_case_studies_header",
            sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
            sa.Column(
                "stats",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "partners",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("NOW()"),
            ),
        )

    exists = bind.execute(
        sa.text("SELECT 1 FROM website_case_studies_header WHERE id = 1")
    ).scalar()
    if not exists:
        bind.execute(
            sa.text(
                "INSERT INTO website_case_studies_header (id, stats, partners, updated_at) "
                "VALUES (1, CAST(:stats AS jsonb), CAST(:partners AS jsonb), NOW())"
            ),
            {
                "stats": json.dumps(DEFAULT_CASE_STUDIES_HEADER_STATS),
                "partners": json.dumps(DEFAULT_CASE_STUDIES_HEADER_PARTNERS),
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("website_case_studies_header"):
        op.drop_table("website_case_studies_header")
