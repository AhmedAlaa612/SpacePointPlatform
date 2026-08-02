"""drop items.is_consumable — every template line now counts toward completeness

Operator decision, 2026-08-01: no item is exempt from a kit's shortage check
any more. Previously an item marked consumable (screws, jumper wire) was
excluded from `kit_shortages`/`expected_counts` entirely, on the theory that
20 screws per kit made a post-workshop count "always short a few" and
therefore unreadable as an alert. The operator wants everything counted
instead — a kit is either fully stocked against its template or it isn't.

Revision ID: a7c9e15f0032
Revises: f4a1c65d0031
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7c9e15f0032"
down_revision = "f4a1c65d0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("items", "is_consumable")


def downgrade() -> None:
    op.add_column(
        "items",
        sa.Column("is_consumable", sa.Boolean(), nullable=False, server_default="false"),
    )
