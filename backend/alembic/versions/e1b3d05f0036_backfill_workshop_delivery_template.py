"""Backfill the `workshop_delivery` system template on databases that never
ran the legacy `sql/0008_template_type.sql` script.

That script was written before this project adopted Alembic and was applied
by hand against production; the Alembic baseline is a schema-only dump, so it
captured the `document_templates.type`/`is_system` columns but not this row.
Any database built from `alembic upgrade head` alone — every local dev
environment — has the columns and no data, silently missing the template
`payments.py` looks up when an instructor signs a payment letter (falls back
to an empty body rather than erroring, so the gap is easy to miss).

Revision ID: e1b3d05f0036
Revises: d8a2c94e0035
Create Date: 2026-08-01
"""

import uuid
import sqlalchemy as sa
from alembic import op

revision = "e1b3d05f0036"
down_revision = "d8a2c94e0035"
branch_labels = None
depends_on = None

BODY_TEXT = (
    "in recognition of his/her outstanding contribution as a facilitator to the "
    "<b>{workshop_name}</b>, delivered on <b>{workshop_date}</b> at <b>{location}</b>"
)


def upgrade() -> None:
    connection = op.get_bind()
    exists = connection.execute(sa.text(
        "SELECT 1 FROM document_templates WHERE key = 'workshop_delivery'"
    )).first()
    if exists:
        return
    connection.execute(
        sa.text(
            "INSERT INTO document_templates (id, key, name, type, is_system, roles, body_text) "
            "VALUES (:id, 'workshop_delivery', 'Workshop Facilitation Certificate', "
            "'certificate', TRUE, ARRAY[]::varchar[], :body_text)"
        ),
        {"id": str(uuid.uuid4()), "body_text": BODY_TEXT},
    )


def downgrade() -> None:
    # Intentionally a no-op: this migration only fills a gap left by a script
    # that already ran against production. Downgrading must not delete a row
    # that predates this migration there — see d8a2c94e0035 for the pattern
    # this deliberately does NOT follow.
    pass
