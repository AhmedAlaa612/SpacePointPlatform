"""merge heads 2/11 (2026-09-30)

Binary merge step — alembic cannot execute an N-way merge (it crashes in
head bookkeeping), so the fragmented tips are unified pairwise. Empty:
no schema change.

Revision ID: b68ce2b52a57
Revises: e7c8b29ec202, a4c1e93f0044
Create Date: 2026-09-30 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = 'b68ce2b52a57'
down_revision = ('e7c8b29ec202', 'a4c1e93f0044')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
