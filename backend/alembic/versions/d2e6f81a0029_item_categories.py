"""item_categories — catalogue grouping becomes editable data, not a hardcoded list.

`items.category` was already a plain VARCHAR(32), never a DB enum or FK — so
this migration is purely additive. It seeds the six names every existing item
already uses, so nothing on `items` needs to change. Same shape as
`delivery_roles` (I5-3): a small ops-editable table backing what was a
hardcoded frontend/backend list.

No `is_active` column — a category is either renamed (which relabels every
item using it, in the same transaction) or deleted outright, and deletion is
refused while any item still uses the name. There is nothing here that a
soft-delete flag would protect that the in-use check doesn't already cover.

Revision ID: d2e6f81a0029
Revises: c4e7a39f0028
Create Date: 2026-08-01
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "d2e6f81a0029"
down_revision = "c4e7a39f0028"
branch_labels = None
depends_on = None

SEED_CATEGORIES = ["board", "sensor", "mechanical", "tool", "merch", "other"]


def upgrade() -> None:
    op.create_table(
        "item_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(32), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    table = sa.table(
        "item_categories",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        table,
        [
            {
                "id": uuid.uuid4(),
                "name": name,
                "sort_order": i,
                "created_at": now,
            }
            for i, name in enumerate(SEED_CATEGORIES)
        ],
    )


def downgrade() -> None:
    op.drop_table("item_categories")
