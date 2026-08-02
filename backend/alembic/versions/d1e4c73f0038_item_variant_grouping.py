"""items.variant_group / variant_label — lightweight size/variant grouping

Operator ask, 2026-08-02: "T-Shirt S/M/L/XL" are five unrelated catalogue rows
today, each with its own name, photo slot and stock count — there is no way
to see "how many T-shirts do we own across sizes" without adding them up by
hand, and no way to browse sizes as one thing.

Deliberately the lightest fix, not the full e-commerce product/variant split:
`stock_levels`, `kit_items` and `movements` still key on `items.id` exactly
as before — nothing about how stock is counted or how custody is recorded
changes. This only adds grouping *metadata* for display: `variant_group` is
the shared name a set of variants is browsed under ("T-Shirt"), `variant_label`
is what tells them apart ("S", "M", "L"). Same shape as `items.category`
(`item_category.py`'s docstring) — a plain string, no FK, no separate table:
there is no signed document reading this, so there is nothing here that
needs a live/frozen split or referential integrity, and a real e-commerce
variant model (shared parent row, child SKUs, stock keyed on the child) is a
bigger change than one afternoon's UI grouping justifies. Revisit if this
grows a rename-cascade or a "manage groups" screen — at that point it may
earn a real table the way `item_categories` did.

`items.name` stays globally unique and distinct per variant ("T-Shirt L", not
"T-Shirt" x5) — custody/movement history already shows which variant someone
holds via that name; this migration doesn't touch that constraint or rename
anything existing.

Revision ID: d1e4c73f0038
Revises: a3c7f95e0037
Create Date: 2026-08-02
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d1e4c73f0038"
down_revision = "a3c7f95e0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("items", sa.Column("variant_group", sa.String(length=128), nullable=True))
    op.add_column("items", sa.Column("variant_label", sa.String(length=32), nullable=True))
    op.create_index("ix_items_variant_group", "items", ["variant_group"])


def downgrade() -> None:
    op.drop_index("ix_items_variant_group", table_name="items")
    op.drop_column("items", "variant_label")
    op.drop_column("items", "variant_group")
