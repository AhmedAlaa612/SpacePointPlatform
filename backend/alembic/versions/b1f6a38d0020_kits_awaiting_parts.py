"""kits.awaiting_parts_since / _note — the storekeeper fulfilment loop (I3-1)

Two nullable columns, and **no fulfilment-task table**. That absence is the
design, so it is worth writing down.

A fulfilment task would be: "kit X is short item Y, someone should fix it".
But the shortage is already computed (`services/inventory/completeness.py`),
and refilling the kit makes it disappear on its own — so the task, its
identity and its closure are all derivable, and a table storing them would
have to be kept in step with the thing it duplicates. The legacy system had
exactly that table (`package_requests`): six rows in thirteen months, one of
them stuck in `on_way` since February. §5 collapsed four such tables into the
movement ledger; this would have been the fifth.

What genuinely cannot be derived is the storekeeper's judgment: *I looked,
and the shelf was empty.* Stock can be replenished tomorrow, so "no stock
right now" is not the same fact as "somebody checked and there was none",
and only the second one tells ops something they didn't already know.

`awaiting_parts_since` is a timestamp rather than a boolean because "waiting
three weeks" is the part worth seeing on a list. When procurement lands
(I4-*), this column becomes the trigger for raising a purchase rather than
the dead end it is today — which is precisely the degradation the operator
accepted when Phase 4 moved last.

Revision ID: b1f6a38d0020
Revises: a8d4f16c0019
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op

revision = "b1f6a38d0020"
down_revision = "a8d4f16c0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("kits", sa.Column("awaiting_parts_since", sa.DateTime(timezone=True), nullable=True))
    op.add_column("kits", sa.Column("awaiting_parts_note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("kits", "awaiting_parts_note")
    op.drop_column("kits", "awaiting_parts_since")
