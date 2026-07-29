"""add 'coo' and 'storekeeper' to user_role enum — inventory phase (I0-2)

`coo` approves inventory actions (purchases, cross-border transfers). `admin`
already passes every RequireRole check, so "an admin can approve in the COO's
place" needs no delegation machinery — the approval record just stores who
actually signed.

`storekeeper` is deliberately narrow: refill kit components, receive goods,
record stock movements. It must NOT reach session assignments, kit
create/edit/delete, programs, cohorts, registrations or contacts — that
restriction is the whole point of the role, not a side effect. It is enforced
by `require_operations` simply not listing it.

Revision ID: c4f9b25e0015
Revises: b3e8a41d0014
Create Date: 2026-07-28
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c4f9b25e0015"
down_revision = "b3e8a41d0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block.
    # Same pattern as b2d8a91c0002 (which added 'operations').
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'coo'")
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'storekeeper'")


def downgrade() -> None:
    # Postgres cannot drop a value from an enum type — no-op by design.
    pass
