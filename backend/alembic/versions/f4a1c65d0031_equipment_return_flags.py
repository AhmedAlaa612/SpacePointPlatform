"""equipment_return_flags — persisted "return later" for non-kit equipment

Session kits already carry their own `return_status`; equipment has no
counterpart because what happened to it lives entirely in the movement
ledger (issue vs. return, netted). This adds the one thing that ledger can't
say on its own — "nothing has moved yet, but the instructor already decided
it's coming back later" — so it survives a reload instead of being purely a
browser-side note, and so it can be toggled the same way a kit's return
report can, right up until the session is marked done.

Revision ID: f4a1c65d0031
Revises: e3f8b04c0030
Create Date: 2026-08-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "f4a1c65d0031"
down_revision = "e3f8b04c0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equipment_return_flags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id", UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "item_id", UUID(as_uuid=True),
            sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "item_id", "user_id", name="uq_equipment_return_flag"),
    )
    op.create_index("ix_equipment_return_flags_session_id", "equipment_return_flags", ["session_id"])
    op.create_index("ix_equipment_return_flags_item_id", "equipment_return_flags", ["item_id"])
    op.create_index("ix_equipment_return_flags_user_id", "equipment_return_flags", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_equipment_return_flags_user_id", table_name="equipment_return_flags")
    op.drop_index("ix_equipment_return_flags_item_id", table_name="equipment_return_flags")
    op.drop_index("ix_equipment_return_flags_session_id", table_name="equipment_return_flags")
    op.drop_table("equipment_return_flags")
