"""Email Templates System — every system email as an editable, pausable row.

Same shape as `document_templates`, but never a create/delete surface: each
`key` is wired to exactly one call site in the code (see
`app/db/email_template_defaults.py`), so the row set is fixed at creation
time and seeded directly here — same pattern as `d2e6f81a0029` (item
categories) and `d8a2c94e0035` (student_completion template row). Production
runs `alembic upgrade head` on every deploy, so the table is never empty on
a fresh environment; `db/seed_email_templates.py` exists only as a manual
re-seed/backfill convenience.

Revision ID: b4e7a19c0038
Revises: c7d2e8a94f5b
Create Date: 2026-08-27
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.db.email_template_defaults import EMAIL_TEMPLATE_DEFAULTS

revision = "b4e7a19c0038"
down_revision = "c7d2e8a94f5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("placeholders", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("attachment_labels", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("is_paused", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    table = sa.table(
        "email_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("key", sa.String),
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("description", sa.Text),
        sa.column("subject", sa.Text),
        sa.column("body_html", sa.Text),
        sa.column("placeholders", postgresql.ARRAY(sa.String())),
        sa.column("attachment_labels", postgresql.ARRAY(sa.String())),
        sa.column("is_internal", sa.Boolean),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        table,
        [
            {
                "id": uuid.uuid4(),
                "key": t["key"],
                "name": t["name"],
                "category": t["category"],
                "description": t["description"],
                "subject": t["subject"],
                "body_html": t["body_html"],
                "placeholders": t["placeholders"],
                "attachment_labels": t["attachment_labels"],
                "is_internal": t["is_internal"],
                "updated_at": now,
            }
            for t in EMAIL_TEMPLATE_DEFAULTS
        ],
    )


def downgrade() -> None:
    op.drop_table("email_templates")
