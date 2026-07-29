"""movements can go into and out of a kit (I1-2 follow-up)

A kit is a container, not just a subject. Without these columns "5 MPUs went
from Dubai into SP-SATKIT-0012" has nowhere to live — `to_location_id` and
`to_user_id` don't cover it, and the subject CHECK forbids setting `item_id`
and `kit_id` together. `from_kit_id` covers the reverse, which happens for
real: cannibalising one kit to make another complete before a workshop.

A separate revision rather than an edit to d5a1c73f0016 because that one is
already applied to the dev and test databases — editing an applied migration
means downgrade/re-upgrade surgery on both, for no benefit. Production has
seen neither and will apply them in sequence.

ondelete is deliberately SET NULL here, unlike the CASCADE on the subject
`movements.kit_id`. The distinction is real: `kit_id` means "this movement is
*about* this kit", so it has no meaning without it — but `to_kit_id` means
"these parts went into that kit", and the fact that the stock left the
warehouse survives the kit being deleted.

Revision ID: e6b2d84a0017
Revises: d5a1c73f0016
Create Date: 2026-07-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "e6b2d84a0017"
down_revision = "d5a1c73f0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "movements",
        sa.Column("from_kit_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "movements",
        sa.Column("to_kit_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_movements_from_kit_id", "movements", "kits",
        ["from_kit_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_movements_to_kit_id", "movements", "kits",
        ["to_kit_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_movements_to_kit_id", "movements", ["to_kit_id"])
    op.create_index("ix_movements_from_kit_id", "movements", ["from_kit_id"])


def downgrade() -> None:
    op.drop_index("ix_movements_from_kit_id", table_name="movements")
    op.drop_index("ix_movements_to_kit_id", table_name="movements")
    op.drop_constraint("fk_movements_to_kit_id", "movements", type_="foreignkey")
    op.drop_constraint("fk_movements_from_kit_id", "movements", type_="foreignkey")
    op.drop_column("movements", "to_kit_id")
    op.drop_column("movements", "from_kit_id")
