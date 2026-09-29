"""merge heads 1/11 (2026-09-30)

Binary merge step — alembic cannot execute an N-way merge (it crashes in
head bookkeeping), so the fragmented tips are unified pairwise. Empty:
no schema change.

Revision ID: e7c8b29ec202
Revises: 8b3d0f61a2c7, 9a46ca83d607
Create Date: 2026-09-30 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = 'e7c8b29ec202'
down_revision = ('8b3d0f61a2c7', '9a46ca83d607')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
