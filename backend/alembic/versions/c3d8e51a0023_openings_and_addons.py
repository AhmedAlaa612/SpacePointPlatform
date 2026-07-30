"""session_openings + session_addons — the offer, per role (I5-4, §G-addons)

`session_openings` is the offer ops types when opening a call: this session
needs 1 Lead Facilitator at 2000 and 2 Assistants at 400. Slots remaining is
`slots` minus assignments and the waitlist is interest beyond that — neither
is stored, both fall out.

`session_addons` is extra money on top. **Attached to the session, not the
opening** (operator, 2026-07-30): add-ons arise at five different moments —
ops opening the call, the instructor's interest response, a specific invite,
the post-session survey, and payment prep — and the opening only exists at
the first. `source` records which moment; `status` (proposed|agreed|declined)
is the entire approval mechanism, since anything an instructor raises is a
request until ops agrees it and anything ops offers is already agreed.

`user_id` NULL means the add-on belongs to the role rather than a person,
which is how the per-opening idea survives without an `opening_id`.

Nothing here touches `PaymentAddon`, which stays the frozen document
snapshot — building a letter copies `agreed` rows into it.

Note this table is additive only: `sessions.staffing_status` is untouched and
still maintained, so everything reading it keeps working while its meaning
tightens from "somebody was assigned" to "every opening filled".

Revision ID: c3d8e51a0023
Revises: c2a7b49e0022
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "c3d8e51a0023"
down_revision = "c2a7b49e0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "session_openings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("role_id", UUID(as_uuid=True),
                  sa.ForeignKey("delivery_roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("slots", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("amount_aed", sa.Numeric(10, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "role_id", name="uq_session_opening_role"),
    )

    op.create_table(
        "session_addons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True),
        # SET NULL, never CASCADE — a departed instructor must not erase the
        # record of money that was agreed (same rule as custody, D1).
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("role_id", UUID(as_uuid=True),
                  sa.ForeignKey("delivery_roles.id", ondelete="SET NULL"), nullable=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("amount_aed", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="offer"),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed"),
        sa.Column("created_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("decided_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("session_addons")
    op.drop_table("session_openings")
